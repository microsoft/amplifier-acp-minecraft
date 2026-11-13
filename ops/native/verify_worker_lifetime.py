"""Pinned latest Instance admission/lifetime with packaged NativeSession.

Actual processes, kernel locks, Worker loops and enrollment journals execute.
The upstream race fixture supplies synthetic OS manager/network boundaries;
this is not production enrollment or another Instance release qualification.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checked_worker(instance):
    pin = json.loads(Path(__file__).with_name('instance-worker-lock.json').read_bytes())
    for name, digest in {pin['path']: pin['sha256'], **pin['files']}.items():
        if hashlib.sha256((instance / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Exact Instance fixture mismatch: ' + name)
    return pin


def main():
    parser = argparse.ArgumentParser()
    for name in ('bundle', 'source', 'shared', 'instance', 'receipt', 'probe_root'):
        parser.add_argument('--' + name.replace('_', '-'), type=Path)
    parser.add_argument('--startup-probe', action='store_true')
    parser.add_argument('--wait-startup', action='store_true')
    args = parser.parse_args()
    instance = args.instance.resolve()
    pin = checked_worker(instance)
    if args.probe_root:
        worker = load(instance / pin['path'], 'latest_worker_probe')
        if args.wait_startup:
            original_guard = worker.enrollment_guard
            @contextlib.contextmanager
            def observed_guard(root):
                try:
                    with original_guard(root):
                        yield
                except worker.LockBusy:
                    marker = root.parent / 'native-admission-observed.json'
                    if not marker.exists():
                        marker.write_text(json.dumps({'pid': os.getpid(), 'actual_lock_busy': True}))
                    raise
            worker.enrollment_guard = observed_guard
            worker.ssl.create_default_context = lambda **kwargs: None
            def once_tick(value):
                assert not value.state.get('enrollment')
                assert value.c == worker.load_registration(value.registration)
                (value.root.parent / 'successor-ready').touch()
            worker.Worker.tick = once_tick  # external API work is synthetic
            worker.run_worker(args.probe_root / 'registration.json', once=True)
            return
        try:
            if args.startup_probe:
                def forbidden(*a, **kw):
                    raise AssertionError('Duplicate startup touched enrollment admission')
                worker.enrollment_guard = forbidden
                worker.run_worker(args.probe_root / 'registration.json', once=True)
            else:
                with worker.single_worker(args.probe_root):
                    pass
        except worker.LockBusy:
            print(json.dumps({'outcome': 'busy'}))
        else:
            print(json.dumps({'outcome': 'acquired'}))
        return

    bundle, shared = args.bundle.resolve(), args.shared.resolve()
    manifest = json.loads((bundle / 'manifest.json').read_bytes())
    sys.path[:0] = [str(bundle / 'app'), str(shared / 'tests/native_python'),
                   str(Path(__file__).resolve().parent)]
    from constellation_native import NativeSession, Busy, initialize_config
    from fixture_security import copy_fixture_driver
    from test_driver import protect
    driver = bundle / manifest['commands']['native_driver']
    library = bundle / manifest['commands']['native_library']
    for role, path in (('driver', driver), ('library', library)):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['native_platform'][role + '_sha256']
    os.environ['CONSTELLATION_ENROLLMENT_SOURCE'] = str(instance / 'ops/updates')
    race = load(instance / 'ops/updates/test_enrollment_race.py', 'latest_enrollment_fixture')

    class PackagedLifetimeTests(race.EnrollmentRaceTests):
        def native_setup(self):
            for path in (self.root, self.home, self.home / 'bin', self.state):
                protect(path)
            for name in ('worker.lock', 'enrollment.lock'):
                path = self.state / name
                path.write_bytes(b'0')
                protect(path)
            self.native_config = self.state / 'native.json'
            initialize_config(driver, self.native_config, {
                'version': 1, 'roots': {'state': str(self.state)},
                'locks': {'worker': str(self.state / 'worker.lock'),
                          'enrollment': str(self.state / 'enrollment.lock')},
                'services': {},
            })
            self.native_driver = copy_fixture_driver(driver, self.state, self.native_config)

        def native(self):
            return NativeSession(library, self.native_driver, self.native_config)

        def probe(self, startup=False):
            command = [sys.executable, '-I', str(Path(__file__).resolve()),
                       '--instance', str(instance), '--probe-root', str(self.state)]
            if startup:
                command.append('--startup-probe')
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)['outcome']

        def test_latest_singleton_contends_with_packaged_native_both_directions(self):
            self.native_setup()
            identity = (self.state / 'worker.lock').stat()
            before = (self.state / 'state.json').read_bytes()
            child = self.child('hold')
            race.wait_file(self.root / 'ready')
            with self.native() as native:
                with self.assertRaises(Busy):
                    with native.lock('worker'):
                        self.fail('Latest Worker singleton must retain its kernel lock')
            (self.root / 'release').touch()
            stdout, stderr = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, stdout + stderr)
            with self.native() as native, native.lock('worker'):
                self.assertEqual(self.probe(), 'busy')
                self.assertEqual(self.probe(startup=True), 'busy')
            self.assertEqual(self.probe(), 'acquired')
            after = (self.state / 'worker.lock').stat()
            self.assertEqual((identity.st_dev, identity.st_ino), (after.st_dev, after.st_ino))
            self.assertEqual((self.state / 'state.json').read_bytes(), before)

        def test_latest_startup_waits_outside_singleton_during_native_admission(self):
            self.native_setup()
            before = (self.state / 'state.json').read_bytes()
            with self.native() as native, native.lock('enrollment'):
                child = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()),
                    '--instance', str(instance), '--probe-root', str(self.state), '--wait-startup'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.processes.append(child)
                # The barrier follows a real failed enrollment-lock attempt,
                # so slow child startup cannot masquerade as admission fencing.
                race.wait_file(self.root / 'native-admission-observed.json')
                self.assertIsNone(child.poll())
                self.assertFalse((self.root / 'successor-ready').exists())
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with native.lock('worker'):
                            self.assertFalse((self.root / 'successor-ready').exists())
                        break
                    except Busy:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(.01)
                self.assertEqual((self.state / 'state.json').read_bytes(), before)
            stdout, stderr = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, stdout + stderr)
            self.assertTrue((self.root / 'successor-ready').exists())
            self.assertEqual((self.state / 'state.json').read_bytes(), before)
            self.assertEqual(self.probe(), 'acquired')

        def test_actual_reporting_thread_blocks_readiness_until_settled(self):
            with patch.object(race.w.ssl, 'create_default_context'):
                worker = race.w.Worker(self.state / 'registration.json')
            entered, release = threading.Event(), threading.Event()
            before = (self.state / 'state.json').read_bytes()
            def report(**kwargs):
                entered.set()
                if not release.wait(20):
                    raise AssertionError('Owned reporting fixture not released')
            worker.report = report
            with worker.reporting():
                try:
                    self.assertTrue(entered.wait(20))  # actual 15-second heartbeat
                    self.assertEqual(len(worker._reporting_threads), 1)
                    self.assertTrue(worker._reporting_threads[0].is_alive())
                    self.assertFalse(worker.enrollment_ready())
                finally:
                    release.set()
            self.assertFalse(any(t.is_alive() for t in worker._reporting_threads))
            self.assertTrue(worker.enrollment_ready())
            self.assertEqual((self.state / 'state.json').read_bytes(), before)

    class Result(unittest.TextTestResult):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.passed = []
        def addSuccess(self, test):
            super().addSuccess(test)
            self.passed.append(test.id())

    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(PackagedLifetimeTests))
    receipt = {'source': manifest['source_commit'], 'target': manifest['target'],
               'fixture_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'worker': pin, 'shared': manifest['native_platform']['source'],
               'driver_sha256': manifest['native_platform']['driver_sha256'],
               'library_sha256': manifest['native_platform']['library_sha256'],
               'tests': result.testsRun, 'passed': result.passed,
               'skipped': [(t.id(), why) for t, why in result.skipped],
               'success': result.wasSuccessful() and not result.skipped and result.testsRun == 13,
               'scope': __doc__, 'production_operations': False}
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    raise SystemExit(0 if receipt['success'] else 1)


if __name__ == '__main__':
    main()
