"""Binding contract fixtures; actual driver/OS conformance runs separately."""
import contextlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from installation_guard import (ContinuityError, durable_write, durable_remove,
                                installation_lock, owner_io)
from installation_native import NativeIO, NativeInstallation, validate_driver_mapping
from test_native_service_evidence import service


class Driver:
    def __init__(self):self.calls=[];self.failure=None
    @contextlib.contextmanager
    def lock(self,name):
        self.calls.append(('lock',name));yield;self.calls.append(('unlock',name))
    def private_dir(self,*args):self.calls.append(('mkdir',*args))
    def private_write(self,*args):self.calls.append(('write',*args))
    def durable_remove(self,*args):self.calls.append(('remove',*args))
    def service_snapshot(self,name):self.calls.append(('snapshot',name));return service()
    def service_action(self,*args):
        self.calls.append(('action',*args))
        if self.failure:raise self.failure
        return {'accepted':True}


class NativeBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cfg={'home':str(self.root/'game'),'state':str(self.root/'owner'),
            'native_platform':{'version':1,'python':str(self.root/'python'),
                'services':{'body':'body','controller':'controller'}}}
        self.driver=Driver()

    def test_invocation_scoped_lock_and_publication_use_fixed_shared_names(self):
        native=NativeIO(self.cfg,self.driver);root=Path(self.cfg['state'])
        with patch('installation_guard.os.open',side_effect=AssertionError('No local POSIX path')):
            with owner_io(native),installation_lock(root/'installation.lock'):
                durable_write(root/'transactions/test.json',{'phase':'intent'})
                durable_remove(Path(self.cfg['home'])/'installation-updates/gate.json')
                self.assertEqual(self.driver.calls[0],('lock','installation'))
                self.assertNotIn(('unlock','installation'),self.driver.calls)
        self.assertEqual(self.driver.calls[-1],('unlock','installation'))
        self.assertIn(('write','state','transactions/test.json',b'{"phase": "intent"}'),self.driver.calls)
        self.assertIn(('remove','home','installation-updates/gate.json'),self.driver.calls)
        # Context ends with this invocation; no global platform mode persists.
        local=self.root/'local.json';durable_write(local,{'local':True})
        self.assertEqual(json.loads(local.read_text()),{'local':True})

    def test_unknown_path_or_lock_never_falls_back(self):
        native=NativeIO(self.cfg,self.driver)
        for path in [self.root/'outside.json',Path(self.cfg['state'])/'../other',Path(self.cfg['home'])]:
            with self.assertRaises(ValueError):native.write(path,{})
        with self.assertRaises(ValueError):
            with native.lock(Path(self.cfg['state'])/'unknown.lock'):pass
        self.assertEqual(self.driver.calls,[])

    def test_native_service_control_uses_original_observation_and_no_redispatch(self):
        backend=NativeInstallation(self.cfg,self.driver)
        with self.assertRaises(ContinuityError):backend.action('controller','stop')
        observed=backend.services();retained=copy.deepcopy(observed['controller'])
        observed['controller']['native']['opaque']='caller-mutated'
        backend.action('controller','stop')
        self.assertEqual(self.driver.calls[-1],('action','controller','stop',retained))
        with self.assertRaises(ContinuityError):backend.action('controller','stop')
        self.assertEqual(backend.session_python(),Path(self.cfg['native_platform']['python']))
        with self.assertRaises(ContinuityError):backend.command('start','anything')

    def test_shared_unknown_exception_propagates_without_another_dispatch(self):
        backend=NativeInstallation(self.cfg,self.driver);backend.services()
        class Unknown(RuntimeError):pass
        failure=Unknown('lost response');self.driver.failure=failure
        with self.assertRaises(Unknown) as raised:backend.action('body','stop')
        self.assertIs(raised.exception,failure)
        with self.assertRaises(ContinuityError):backend.action('body','stop')
        self.assertEqual(sum(c[0]=='action' for c in self.driver.calls),1)

    def test_mapping_requires_the_same_roots_lock_and_services(self):
        path=self.root/'driver.json'
        config={'version':1,'roots':{k:self.cfg[k] for k in ('home','state')},
            'locks':{'installation':str(Path(self.cfg['state'])/'installation.lock')},
            'services':{'body':{},'controller':{}}}
        path.write_text(json.dumps(config));validate_driver_mapping(self.cfg,path)
        config['roots']['home']=str(self.root/'different');path.write_text(json.dumps(config))
        with self.assertRaises(ValueError):validate_driver_mapping(self.cfg,path)

if __name__=='__main__':unittest.main()
