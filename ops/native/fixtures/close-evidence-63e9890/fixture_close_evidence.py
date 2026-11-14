"""Best-effort test cleanup observations; never an owner or cleanup mechanism.

Only an exact driver Popen is observed. Children and their original methods are
weakly referenced. Native observations borrow Popen's existing Windows handle;
they neither open/duplicate/close it nor wait beyond a zero-time query. Errors
in evidence collection are unavailable evidence, never fixture verdicts.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import sys
import time
import weakref


MAX_CHILDREN = 32
MAX_EVENTS = 128
MAX_JSON_BYTES = 65536


def _error(error):
    result = {"type": type(error).__name__[:80]}
    for key in ("errno", "winerror"):
        value = getattr(error, key, None)
        if type(value) is int:
            result[key] = value
    return result


def _number(value):
    return value if type(value) is int else None


def _native_handle_snapshot(process):
    """Borrow only; no OpenProcess, DuplicateHandle or CloseHandle."""
    if os.name != "nt":
        return {"state": "not_windows"}
    handle = vars(process).get("_handle")
    if handle is None:
        return {"state": "unavailable", "reason": "no_existing_handle"}
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    wait = kernel.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    times = kernel.GetProcessTimes
    times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    times.restype = wintypes.BOOL
    image = kernel.QueryFullProcessImageNameW
    image.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                      ctypes.POINTER(wintypes.DWORD)]
    image.restype = wintypes.BOOL
    borrowed = wintypes.HANDLE(int(handle))
    observed = int(wait(borrowed, 0))
    result = {"wait": observed, "state": {0: "exited", 258: "live"}.get(observed, "unknown")}
    if observed not in (0, 258):
        result["wait_error"] = ctypes.get_last_error()
    stamps = [wintypes.FILETIME() for _ in range(4)]
    if times(borrowed, *(ctypes.byref(item) for item in stamps)):
        result["creation_filetime"] = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
    else:
        result["times_error"] = ctypes.get_last_error()
    # Some exited Windows processes reject image queries. Preserve wait/birth
    # evidence and any earlier image, rather than turning this into no evidence.
    if observed == 258:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if image(borrowed, 0, buffer, ctypes.byref(size)):
            path = buffer.value
            result["image"] = path[:512]
            result["image_truncated"] = len(path) > 512
            result["image_sha256"] = hashlib.sha256(path.encode("utf-8")).hexdigest()
        else:
            result["image_error"] = ctypes.get_last_error()
    else:
        result["image_query"] = "not_attempted_after_nonlive_wait"
    return result


class CleanupEvidence:
    def __init__(self, test_id, driver):
        self.test_id = str(test_id)[:256]
        self.driver = os.path.normcase(os.path.abspath(os.fspath(driver)))
        self._children = []  # (weakref, content-free mutable record)
        self._events = []
        self._dropped = 0
        self._unavailable = 0
        self._started = time.monotonic()

    def _safe(self, function, fallback=None):
        try:
            return function()
        except BaseException:
            self._unavailable += 1
            return fallback

    def _event(self, name, **fields):
        if len(self._events) >= MAX_EVENTS:
            self._dropped += 1
            return
        self._events.append({"event": name, "elapsed": round(time.monotonic() - self._started, 6), **fields})

    def _process(self, process, record):
        value = {"pid": _number(getattr(process, "pid", None)),
                 "returncode": _number(getattr(process, "returncode", None))}
        try:
            value["native"] = _native_handle_snapshot(process)
        except BaseException as error:
            value["native"] = {"state": "unknown", "error": _error(error)}
        image = value["native"].get("image")
        if image is not None:
            record["last_image"] = image
            record["last_image_sha256"] = value["native"]["image_sha256"]
        if "last_image" in record:
            value["last_observed_image"] = record["last_image"]
            value["last_observed_image_sha256"] = record["last_image_sha256"]
        record["last"] = value
        return value

    def _track(self, process, mode):
        if len(self._children) >= MAX_CHILDREN:
            self._dropped += 1
            return
        ref = weakref.ref(process)
        record = {"child": len(self._children) + 1, "mode": mode}
        self._children.append((ref, record))
        self._event("popen_returned", child=record["child"], process=self._process(process, record))
        for name in ("wait", "kill"):
            # Capturing a bound method here would extend Popen/handle lifetime.
            # Unsupported callable forms are left untouched, explicitly unknown.
            try:
                original = weakref.WeakMethod(getattr(process, name))
                wrapper = self._method_wrapper(original, ref, record, name)
                setattr(process, name, wrapper)
            except BaseException as error:
                self._event("method_unobserved", child=record["child"], method=name, error=_error(error))

    def _method_wrapper(self, method_ref, process_ref, record, name):
        def observed(*args, **kwargs):
            # The process remains live in the caller while its method executes.
            # These temporary strong references do not escape this call.
            method = method_ref()
            if method is None:
                raise ReferenceError("Observed process method is no longer available")
            process = process_ref()
            started = self._safe(time.monotonic)
            fields = {"child": record["child"], "method": name}
            if name == "wait":
                timeout = kwargs.get("timeout", args[0] if args else None)
                fields["timeout_seconds"] = self._safe(
                    lambda: timeout if type(timeout) in (int, float) and math.isfinite(timeout) else None)
            self._safe(lambda: self._event("method_before", **fields,
                       process=self._process(process, record)))
            try:
                result = method(*args, **kwargs)
            except BaseException as error:
                self._safe(lambda: self._event("method_after", **fields, outcome="raised", error=_error(error),
                           seconds=None if started is None else time.monotonic() - started,
                           process=self._process(process, record)))
                raise
            self._safe(lambda: self._event("method_after", **fields, outcome="returned", result=_number(result),
                       seconds=None if started is None else time.monotonic() - started,
                       process=self._process(process, record)))
            return result
        return observed

    def _scope(self, args, kwargs):
        argv = args[0] if args else kwargs.get("args")
        if kwargs.get("shell") or not isinstance(argv, (list, tuple)) or not argv:
            return None
        executable = kwargs.get("executable", argv[0])
        if executable is None:
            executable = argv[0]
        if any(os.path.normcase(os.path.abspath(os.fspath(value))) != self.driver
               for value in (argv[0], executable)):
            return None
        return "initialize" if len(argv) > 1 and argv[1] == "initialize" else "driver"

    def popen_factory(self, original):
        def spawn(*args, **kwargs):
            mode = self._safe(lambda: self._scope(args, kwargs))
            try:
                process = original(*args, **kwargs)
            except BaseException as error:
                if mode is not None:
                    self._safe(lambda: self._event("popen_raised", mode=mode, error=_error(error)))
                raise
            if mode is not None:
                self._safe(lambda: self._track(process, mode))
            return process
        return spawn

    def _session(self, session):
        value = {"closed": getattr(session, "_closed", None)}
        fields = vars(session)
        if "_handle" in fields and "_process" not in fields:
            value.update(kind="native", token=_number(getattr(fields["_handle"], "value", None)),
                         depth=_number(fields.get("_depth")))
        elif "_process" in fields:
            value["kind"] = "cli"
            process = fields["_process"]
            value["pid"] = _number(getattr(process, "pid", None))
            value["returncode"] = _number(getattr(process, "returncode", None))
            reader = fields.get("_reader")
            value["reader_alive"] = reader.is_alive() if reader is not None else None
            value["streams"] = {name: None if getattr(process, name, None) is None else
                                bool(getattr(process, name).closed) for name in ("stdin", "stdout", "stderr")}
        else:
            value["kind"] = "unknown"
        return value

    def close_session(self, session):
        self._safe(lambda: self._event("session_close_before", session=self._session(session)))
        started = self._safe(time.monotonic)
        try:
            result = session.close()
        except BaseException as error:
            self._safe(lambda: self._event("session_close_after", outcome="raised", error=_error(error),
                       seconds=None if started is None else time.monotonic() - started,
                       session=self._session(session)))
            raise
        self._safe(lambda: self._event("session_close_after", outcome="returned",
                   seconds=None if started is None else time.monotonic() - started,
                   session=self._session(session)))
        return result

    def cleanup_directory(self, temporary):
        self._safe(lambda: self._event("directory_cleanup_before", children=self._child_snapshots()))
        started = self._safe(time.monotonic)
        try:
            result = temporary.cleanup()
        except BaseException as error:
            self._safe(lambda: self._event("directory_cleanup_after", outcome="raised", error=_error(error),
                       seconds=None if started is None else time.monotonic() - started))
            raise
        self._safe(lambda: self._event("directory_cleanup_after", outcome="returned",
                   seconds=None if started is None else time.monotonic() - started))
        return result

    def _child_snapshots(self):
        children = []
        for ref, record in self._children:
            process = ref()
            children.append({"child": record["child"], "mode": record["mode"],
                             "object_collected": process is None,
                             "observed": record.get("last") if process is None else self._process(process, record)})
        return children

    def report(self):
        def collect():
            value = {"schema": 1, "fixture_cleanup_evidence": True, "test_id": self.test_id,
                     "children": self._child_snapshots(), "events": list(self._events), "dropped": self._dropped,
                     "observer_unavailable": self._unavailable,
                     "observer_owns_no_process_or_cleanup": True}
            while len(json.dumps(value, ensure_ascii=True).encode()) > MAX_JSON_BYTES:
                if value["events"]:
                    value["events"].pop(0)
                elif value["children"]:
                    value["children"].pop()
                else:
                    break
                value["dropped"] += 1
            return value
        return self._safe(collect, {"schema": 1, "fixture_cleanup_evidence": True,
                                    "test_id": self.test_id, "observer_unavailable": True})

    def emit(self, stream=None):
        self._safe(lambda: print(json.dumps(self.report(), ensure_ascii=True),
                                 file=sys.stderr if stream is None else stream, flush=True))
