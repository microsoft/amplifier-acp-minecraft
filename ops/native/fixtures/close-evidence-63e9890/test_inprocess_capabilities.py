"""Compose scoped cleanup and data snapshots with actual caller-owned locks.

Native effects use the supplied matched library/driver. Fault injection only
changes Python response consumption after the actual operation has returned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from test_driver import protect
from test_tree import TreeFixture
from fixture_close_evidence import CleanupEvidence
from constellation_native import Busy, DriverError, NativeSession, Refused, Session, Unknown
from constellation_native import client as native_client

LIBRARY = os.environ.get("CONSTELLATION_NATIVE_LIBRARY")
DRIVER = os.environ.get("CONSTELLATION_NATIVE_DRIVER")


class InprocessCapabilitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not LIBRARY or not DRIVER:
            if os.environ.get("CI", "").lower() == "true":
                raise AssertionError("CI requires the matched native library and driver")
            raise unittest.SkipTest("Set CONSTELLATION_NATIVE_LIBRARY and CONSTELLATION_NATIVE_DRIVER")
        cls.library = str(Path(LIBRARY).resolve(strict=True))
        cls.driver_input = Path(DRIVER).resolve(strict=True)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(
            prefix="native-combined-", dir=os.environ.get("CONSTELLATION_NATIVE_TEST_ROOT")
        )
        self.cleanup_evidence = None
        self.addCleanup(self._cleanup_temporary, temporary)
        self.base = Path(temporary.name).resolve()
        self.driver = self.base / ("driver.exe" if os.name == "nt" else "driver")
        self.cleanup_evidence = CleanupEvidence(self.id(), self.driver)
        protect(self.base)
        shutil.copyfile(self.driver_input, self.driver)
        protect(self.driver)
        if os.name != "nt":
            self.driver.chmod(0o700)
        # Observe the actual initializer children as well as the later CLI
        # invocation. The observer does not keep processes/handles alive or
        # change their existing wait, kill, close or directory-removal behavior.
        process_observer = mock.patch.object(
            native_client.subprocess, "Popen",
            new=self.cleanup_evidence.popen_factory(native_client.subprocess.Popen),
        )
        process_observer.start()
        self.addCleanup(process_observer.stop)
        self.fixture = TreeFixture(self.base, str(self.driver))
        self.first = self.native()
        self.second = self.native()

    def _cleanup_temporary(self, temporary):
        if self.cleanup_evidence is None:
            temporary.cleanup()
            return
        try:
            self.cleanup_evidence.cleanup_directory(temporary)
        finally:
            self.cleanup_evidence.emit()

    def native(self):
        native = NativeSession(self.library, self.driver, self.fixture.config)
        self.addCleanup(self.cleanup_evidence.close_session, native)
        return native

    def cli(self):
        session = Session(self.driver, self.fixture.config)
        self.addCleanup(self.cleanup_evidence.close_session, session)
        return session

    def assert_contended(self):
        with self.assertRaises(Busy):
            with self.second.lock("installation"):
                self.fail("Response consumption released the caller's kernel lock")

    def test_both_bindings_advertise_all_combined_capabilities(self):
        for native in (self.first, self.cli()):
            description = native.describe()
            for capability, operation in (
                ("regenerable_tree_observation", "tree.observe"),
                ("private_data_publication", "storage.write_data"),
                ("private_data_read", "storage.read_data"),
            ):
                self.assertEqual(description[capability], 1)
                self.assertIn(operation, description["operations"])
        self.assertFalse(hasattr(self.first, "_process"))

    def test_cli_and_native_publish_and_read_the_same_protected_bytes(self):
        cli = self.cli()
        original = b'{"phase":"prepared"}\x00\xff'
        replacement = b'{"phase":"committed"}\n'
        with self.first.lock("installation"):
            self.assertIsNone(self.first.private_read_data("state", "journal.json"))
            self.first.private_write_data("state", "journal.json", original)
            self.assertEqual(cli.private_read_data("state", "journal.json"), original)
            self.assert_contended()
        with cli.lock("installation"):
            cli.private_write_data("state", "journal.json", replacement)
            self.assertEqual(self.first.private_read_data("state", "journal.json"), replacement)
            with self.assertRaises(Refused) as caught:
                self.first.private_write("state", "journal.json", b"wrong", create_only=True)
            self.assertEqual(caught.exception.code, "already_exists")
        with self.first.lock("installation"):
            self.first.private_write_data("state", "journal.json", b"")
            self.assertEqual(self.first.private_read_data("state", "journal.json"), b"")
            self.first.durable_remove("state", "journal.json")
            self.assertIsNone(self.first.private_read_data("state", "journal.json"))
        self.fixture.assert_outside()

    def test_correlated_read_refusal_keeps_session_and_kernel_ownership(self):
        with self.first.lock("installation"):
            self.first.private_write_data("state", "journal.json", b"complete")
            with self.assertRaises(Refused) as caught:
                self.first.private_read_data("state", "journal.json", max_bytes=2)
            self.assertEqual(caught.exception.code, "data_too_large")
            self.assertFalse(self.first._poisoned)
            self.assert_contended()
            self.assertEqual(self.first.private_read_data("state", "journal.json"), b"complete")
            for value in (True, 0, 1048577, 1.0, None):
                with self.assertRaises(ValueError):
                    self.first.private_read_data("state", "journal.json", max_bytes=value)
            self.assertFalse(self.first._poisoned)

    def test_scoped_intent_survives_committed_removal_decode_loss_without_retry(self):
        entry = self.fixture.entry()
        (entry / "disposable").write_bytes(b"regenerable")
        interrupt = KeyboardInterrupt("fixture consumes no committed reply")
        with mock.patch.object(self.first, "_call", wraps=self.first._call) as dispatch:
            with self.first.lock("installation"):
                observed = self.first.tree_observe("stages", "candidate")
                intent = {"phase": "pruning", "profile": "stages", "entry": "candidate",
                          "scope": observed["scope"]}
                self.first.private_write_data("state", "journal.json", json.dumps(intent).encode())
                with mock.patch.object(self.first, "_guarded_decode", side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        self.first.tree_remove("stages", "candidate", observed["entry"])
                self.assertIs(caught.exception, interrupt)
                self.assertFalse(entry.exists())
                self.assertTrue(self.first._poisoned)
                self.assert_contended()
                with self.assertRaises(Unknown):
                    self.first.tree_observe("stages", "candidate")
            deletes = [call for call in dispatch.call_args_list if call.args[0] == "tree.remove"]
            self.assertEqual(len(deletes), 1)
        self.first.close()
        fresh = self.native()
        with fresh.lock("installation"):
            saved = json.loads(fresh.private_read_data("state", "journal.json"))
            current = fresh.tree_observe(saved["profile"], saved["entry"])
            self.assertEqual(current["scope"], saved["scope"])
            self.assertIsNone(current["entry"])
            # This read proves the domain may settle this same intent; the
            # binding itself does not choose, rewrite, or retry the transaction.
            self.assertEqual(saved, intent)
        self.fixture.assert_outside()

    def test_absence_after_root_replacement_does_not_match_saved_scope(self):
        with self.first.lock("installation"):
            original = self.first.tree_observe("stages", "missing")
            self.assertIsNone(original["entry"])
        self.first.close()
        original_root = self.fixture.stages.with_name("retained-stages")
        self.fixture.stages.rename(original_root)
        from constellation_native import initialize_root
        initialize_root(self.driver, self.fixture.stages)
        fresh = self.native()
        with fresh.lock("installation"):
            current = fresh.tree_observe("stages", "missing")
        self.assertIsNone(current["entry"])
        self.assertNotEqual(current["scope"], original["scope"])
        self.assertTrue(original_root.is_dir())
        self.fixture.assert_outside()

    def _read_fault_retains_ownership(self, result, expected_error):
        with self.first.lock("installation"):
            self.first.private_write_data("state", "journal.json", b"retained")
            original_call = self.first._call
            dispatches = []

            def after_actual_read(op, **fields):
                actual = original_call(op, **fields)
                if op == "storage.read_data":
                    dispatches.append(op)
                    return result
                return actual

            with mock.patch.object(self.first, "_call", side_effect=after_actual_read):
                with self.assertRaises(expected_error):
                    self.first.private_read_data("state", "journal.json")
            self.assertEqual(dispatches, ["storage.read_data"])
            self.assertTrue(self.first._poisoned)
            self.assert_contended()
            with self.assertRaises(Unknown):
                self.first.private_write_data("state", "journal.json", b"must not replace")
            self.assertEqual((self.fixture.state / "journal.json").read_bytes(), b"retained")
        with self.second.lock("installation"):
            self.assertEqual(self.second.private_read_data("state", "journal.json"), b"retained")

    def test_malformed_snapshot_poisons_without_releasing_caller_lock(self):
        self._read_fault_retains_ownership({"present": True, "bytes": [256]}, DriverError)

    def test_snapshot_validation_interrupt_poisons_without_releasing_caller_lock(self):
        class InterruptedBytes(list):
            def __iter__(self):
                raise KeyboardInterrupt("fixture interrupted snapshot validation")
        self._read_fault_retains_ownership(
            {"present": True, "bytes": InterruptedBytes([1])}, KeyboardInterrupt
        )

    @unittest.skipUnless(os.name == "nt", "Actual Windows data-sharing behavior")
    def test_windows_native_data_publication_preserves_held_old_reader(self):
        from test_storage_data import windows_reader
        with self.first.lock("installation"):
            self.first.private_write_data("state", "journal.json", b"original")
            with windows_reader(self.fixture.state / "journal.json") as old:
                self.first.private_write_data("state", "journal.json", b"replacement")
                self.assertEqual(old.read(), b"original")
                self.assertEqual(self.second.private_read_data("state", "journal.json"), b"replacement")
                self.assert_contended()


if __name__ == "__main__":
    unittest.main()
