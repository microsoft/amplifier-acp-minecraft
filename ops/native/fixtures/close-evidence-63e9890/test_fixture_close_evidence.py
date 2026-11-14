"""Pure observer checks; no driver, native library, child, manager or host use."""

import ctypes
import gc
import io
import json
import os
import subprocess
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import patch

import fixture_close_evidence as evidence


class Process:
    def __init__(self):
        self.pid = 42
        self.returncode = None
        self.wait_calls = []
        self.kill_calls = 0
        self.failure = None
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = None

    def wait(self, *args, **kwargs):
        self.wait_calls.append((args, kwargs))
        if self.failure is not None:
            raise self.failure
        self.returncode = 0
        return 0

    def kill(self):
        self.kill_calls += 1
        return None


class FixtureCloseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.driver = os.path.abspath("fixed-driver")
        self.observer = evidence.CleanupEvidence(self.id(), self.driver)

    def track(self, process=None):
        process = Process() if process is None else process
        result = self.observer.popen_factory(lambda *a, **k: process)([self.driver, "initialize"])
        self.assertIs(result, process)
        return process

    def test_exact_four_initializer_children_and_cli_are_observed(self):
        children = []
        def factory(*args, **kwargs):
            process = Process()
            children.append(process)
            return process
        wrapper = self.observer.popen_factory(factory)
        for unused in range(4):
            wrapper([self.driver, "initialize"]).wait(timeout=1)
        wrapper([self.driver, "--config", "NEVER-LOG-CONFIG", "serve"]).wait(timeout=1)
        report = self.observer.report()
        self.assertEqual(len(report["children"]), 5)
        self.assertEqual([c["mode"] for c in report["children"]], ["initialize"] * 4 + ["driver"])
        self.assertNotIn("NEVER-LOG-CONFIG", json.dumps(report))
        self.assertTrue(all(len(c.wait_calls) == 1 and c.kill_calls == 0 for c in children))

    def test_original_timeout_identity_arguments_and_no_added_wait_or_kill(self):
        process = self.track()
        failure = subprocess.TimeoutExpired("SECRET-COMMAND", 1, output=b"SECRET")
        process.failure = failure
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            process.wait(timeout=1)
        self.assertIs(caught.exception, failure)
        process.kill()
        self.observer.report()
        self.assertEqual(process.wait_calls, [((), {"timeout": 1})])
        self.assertEqual(process.kill_calls, 1)
        self.assertNotIn("SECRET", json.dumps(self.observer.report()))
        waits = [event for event in self.observer.report()["events"]
                 if event.get("method") == "wait"]
        self.assertEqual([event["timeout_seconds"] for event in waits], [1, 1])

    def test_original_kill_error_identity_and_single_call(self):
        failure = OSError(5, "PRIVATE")
        class RefusingProcess(Process):
            def kill(self):
                self.kill_calls += 1
                raise failure
        process = self.track(RefusingProcess())
        with self.assertRaises(OSError) as caught:
            process.kill()
        self.assertIs(caught.exception, failure)
        self.assertEqual(process.kill_calls, 1)
        self.assertEqual(process.wait_calls, [])

    def test_huge_wait_timeout_projection_cannot_change_original_call(self):
        process = self.track()
        timeout = 10 ** 500
        failure = ValueError("original wait rejected timeout")
        process.failure = failure
        with self.assertRaises(ValueError) as caught:
            process.wait(timeout=timeout)
        self.assertIs(caught.exception, failure)
        self.assertEqual(process.wait_calls, [((), {"timeout": timeout})])
        self.assertGreater(self.observer.report()["observer_unavailable"], 0)

    def test_observer_holds_neither_process_nor_bound_method(self):
        process = self.track()
        ref = weakref.ref(process)
        del process
        gc.collect()
        self.assertIsNone(ref())
        self.assertTrue(self.observer.report()["children"][0]["object_collected"])

    def test_other_executable_shell_and_override_are_not_modified(self):
        for argv, kwargs in (([self.driver + "-other"], {}), ([self.driver], {"shell": True}),
                             ([self.driver], {"executable": self.driver + "-other"})):
            process = Process()
            before = dict(vars(process))
            self.assertIs(self.observer.popen_factory(lambda *a, **k: process)(argv, **kwargs), process)
            self.assertEqual(vars(process), before)
        self.assertEqual(self.observer.report()["children"], [])

    def test_creation_error_identity_and_no_secret_message(self):
        failure = OSError(5, "PRIVATE-PATH")
        def factory(*args, **kwargs):
            raise failure
        with self.assertRaises(OSError) as caught:
            self.observer.popen_factory(factory)([self.driver])
        self.assertIs(caught.exception, failure)
        self.assertNotIn("PRIVATE-PATH", json.dumps(self.observer.report()))

    def test_native_close_once_before_after_token_depth_and_closed(self):
        class Session:
            _handle = None
            def __init__(self):
                self._handle = ctypes.c_uint64(7)
                self._depth = 0
                self._closed = False
                self.calls = 0
            def close(self):
                self.calls += 1
                self._handle.value = 0
                self._closed = True
                return sentinel
        sentinel = object()
        session = Session()
        self.assertIs(self.observer.close_session(session), sentinel)
        self.assertEqual(session.calls, 1)
        before, after = self.observer.report()["events"]
        self.assertEqual(before["session"]["token"], 7)
        self.assertEqual(after["session"]["token"], 0)
        self.assertTrue(after["session"]["closed"])

    def test_close_and_cleanup_original_baseexception_identity(self):
        for method in (self.observer.close_session, self.observer.cleanup_directory):
            for failure in (RuntimeError("PRIVATE"), KeyboardInterrupt("PRIVATE")):
                calls = []
                def raise_once():
                    calls.append(True)
                    raise failure
                target = SimpleNamespace(close=raise_once, cleanup=raise_once)
                with self.assertRaises(type(failure)) as caught:
                    method(target)
                self.assertIs(caught.exception, failure)
                self.assertEqual(calls, [True])
        self.assertNotIn("PRIVATE", json.dumps(self.observer.report()))

    def test_cli_reader_and_stream_states_are_observed_without_join(self):
        process = self.track()
        calls = []
        class Reader:
            def is_alive(self):
                return not process.stdout.closed
        class Session:
            def __init__(self):
                self._process, self._reader, self._closed = process, Reader(), False
            def close(self):
                calls.append(True)
                process.wait(timeout=1)
                process.stdin.close()
                process.stdout.close()
                self._closed = True
        self.observer.close_session(Session())
        events = self.observer.report()["events"]
        before = next(e for e in events if e["event"] == "session_close_before")
        after = next(e for e in events if e["event"] == "session_close_after")
        self.assertTrue(before["session"]["reader_alive"])
        self.assertFalse(after["session"]["reader_alive"])
        self.assertEqual(after["session"]["streams"], {"stdin": True, "stdout": True, "stderr": None})
        self.assertEqual(calls, [True])
        self.assertEqual(process.wait_calls, [((), {"timeout": 1})])

    def test_observer_failure_cannot_replace_success_or_original_error(self):
        process = self.track()
        with patch.object(self.observer, "_event", side_effect=KeyboardInterrupt("observer")):
            self.assertEqual(process.wait(timeout=1), 0)
            failure = subprocess.TimeoutExpired("private", 1)
            process.failure = failure
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                process.wait(timeout=1)
            self.assertIs(caught.exception, failure)
            calls = []
            value = object()
            temporary = SimpleNamespace(cleanup=lambda: (calls.append(True), value)[1])
            self.assertIs(self.observer.cleanup_directory(temporary), value)
            self.assertEqual(calls, [True])
        self.assertGreater(self.observer.report()["observer_unavailable"], 0)

    def test_native_error_is_unknown_and_never_a_fixture_failure(self):
        with patch.object(evidence, "_native_handle_snapshot", side_effect=OSError(6, "PRIVATE")):
            process = self.track()
            self.assertEqual(process.wait(), 0)
            result = self.observer.report()["children"][0]["observed"]["native"]
        self.assertEqual(result, {"state": "unknown", "error": {"type": "OSError", "errno": 6}})

    def test_emit_failure_in_finally_preserves_original_cleanup_error(self):
        failure = PermissionError(32, "PRIVATE")
        def cleanup():
            raise failure
        class Broken:
            def write(self, value):
                raise KeyboardInterrupt("observer output failed")
        with self.assertRaises(PermissionError) as caught:
            try:
                self.observer.cleanup_directory(SimpleNamespace(cleanup=cleanup))
            finally:
                self.observer.emit(Broken())
        self.assertIs(caught.exception, failure)

    def test_child_snapshot_precedes_cleanup_and_never_pins_collected_child(self):
        process = self.track()
        collected = self.track()
        ref = weakref.ref(collected)
        del collected
        gc.collect()
        native_reads = []
        def native(value):
            native_reads.append(value.pid)
            return {"state": "exited", "wait": 0, "creation_filetime": 123}
        def cleanup():
            self.assertEqual(native_reads, [42])
            before = self.observer._events[-1]
            self.assertEqual(before["event"], "directory_cleanup_before")
            self.assertEqual(before["children"][0]["observed"]["native"]["wait"], 0)
            self.assertTrue(before["children"][1]["object_collected"])
            self.assertIsNone(ref())
        with patch.object(evidence, "_native_handle_snapshot", side_effect=native):
            self.observer.cleanup_directory(SimpleNamespace(cleanup=cleanup))
        self.assertEqual(process.wait_calls, [])
        self.assertEqual(process.kill_calls, 0)

    def test_output_bounded_and_emit_failure_does_not_raise(self):
        self.observer.test_id = "x" * 256
        process = self.track()
        for unused in range(300):
            process.wait()
        output = io.StringIO()
        self.observer.emit(output)
        self.assertLessEqual(len(output.getvalue().encode()), evidence.MAX_JSON_BYTES + 1)
        self.assertGreater(json.loads(output.getvalue())["dropped"], 0)
        class Broken:
            def write(self, value):
                raise OSError("private")
        self.observer.emit(Broken())


if __name__ == "__main__":
    unittest.main()
