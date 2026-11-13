"""Minecraft scope wiring; real library checks are explicitly opt-in."""
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from installation_guard import ContinuityError, current_owner_io, durable_write, installation_lock
from installation_native import NativeIO, native_scope

OPS=['lock.acquire','lock.release','process.identity','service.snapshot',
     'service.action','storage.write','storage.mkdir','storage.remove',
     'tree.inspect','tree.remove']
class Peer:
    def __init__(self,*args):self.args=args;self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*args):self.calls.append(('closed',))
    def describe(self):return {'protocol':1,'operations':OPS,'regenerable_tree_removal':1}
    def tree_remove(self,*args,**kwargs):self.calls.append(('remove',args,kwargs));return {'absent':True}

class NativeCallerScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.lib=self.root/'native-library'
        self.lib.write_bytes(b'fixed test library, not loaded')
        self.driver=self.root/'driver';self.config=self.root/'driver.json'
        self.cfg={'home':str(self.root/'home'),'state':str(self.root/'state'),
                  'native_platform':{'version':1,'driver':str(self.driver),'config':str(self.config),
                     'library':str(self.lib),'library_sha256':hashlib.sha256(self.lib.read_bytes()).hexdigest()}}
        self.config.write_text(json.dumps({'version':1,'roots':{k:self.cfg[k] for k in ('home','state')},
            'locks':{'installation':str(self.root/'state/installation.lock')},
            'services':{'body':{},'controller':{}}}))
    def test_library_driver_config_passed_exactly_without_transport_timeout(self):
        with native_scope(self.cfg,session_factory=Peer,cleanup_deadline=500) as session:
            self.assertEqual(session.args,(self.lib,self.driver,self.config))
            self.assertTrue(current_owner_io().inprocess)
            with patch('installation_native.time.monotonic',return_value=0):
                self.assertIsNone(current_owner_io().tree_removal_timeout())
        self.assertIsNone(current_owner_io());self.assertEqual(session.calls,[('closed',)])
    def test_changed_library_refuses_before_session_load(self):
        self.lib.write_bytes(b'different')
        with patch('installation_native.NativeIO') as io, self.assertRaises(ContinuityError):
            with native_scope(self.cfg,session_factory=lambda *a:self.fail('must not load')):pass
        io.assert_not_called()
    def test_incomplete_relative_or_nonordinary_library_refuses(self):
        native=self.cfg['native_platform']
        cases=[{'library':'relative'},{'library_sha256':None},{'library_sha256':'A'*64},{'library':str(self.root)}]
        for changed in cases:
            with self.subTest(changed=changed),patch.dict(native,changed),self.assertRaises(ValueError):
                with native_scope(self.cfg,session_factory=lambda *a:self.fail('must not load')):pass
    def test_legacy_transport_still_uses_original_two_argument_scope(self):
        del self.cfg['native_platform']['library'];del self.cfg['native_platform']['library_sha256']
        with native_scope(self.cfg,session_factory=Peer,cleanup_deadline=500) as session:
            self.assertEqual(session.args,(self.driver,self.config));self.assertFalse(current_owner_io().inprocess)
            with patch('installation_native.time.monotonic',return_value=0):
                self.assertEqual(current_owner_io().tree_removal_timeout(),120)
    def test_synchronous_cleanup_retains_admission_budget_but_no_call_timeout(self):
        peer=Peer();io=NativeIO(self.cfg,peer,cleanup_deadline=500)
        identifier='ac4a57c2-f4f6-45f4-b8e9-d13ced658a7f'
        with patch('installation_native.time.monotonic',return_value=0):
            with self.assertRaisesRegex(ValueError,'per-call timeout'):
                io.tree_remove('stage',identifier,{'identity':'original'},timeout=120)
            self.assertEqual(peer.calls,[])
            io.tree_remove('stage',identifier,{'identity':'original'})
        self.assertEqual(peer.calls,[('remove',('stages',identifier,{'identity':'original'}),{})])
        with patch('installation_native.time.monotonic',return_value=420),self.assertRaises(ContinuityError):
            io.tree_remove('stage',identifier,{'identity':'original'})
        self.assertEqual(len(peer.calls),1)

@unittest.skipUnless(os.environ.get('MINECRAFT_NATIVE_LIBRARY') and os.environ.get('MINECRAFT_NATIVE_DRIVER'), 'exact paired native candidate required')
class ActualNativeCallerTests(unittest.TestCase):
    def test_domain_scope_owns_kernel_lock_through_direct_python_and_journal_work(self):
        from constellation_native import Session, Busy, initialize_root, initialize_config
        import shutil
        with tempfile.TemporaryDirectory(prefix='minecraft-caller-lock-') as temp:
            root=Path(temp).resolve();driver=root/Path(os.environ['MINECRAFT_NATIVE_DRIVER']).name
            shutil.copyfile(os.environ['MINECRAFT_NATIVE_DRIVER'],driver);driver.chmod(0o700)
            lib=Path(os.environ['MINECRAFT_NATIVE_LIBRARY']).resolve()
            home=root/'home';state=root/'state'
            for p in (home,state):initialize_root(driver,p)
            config=state/'driver.json'
            manager={'linux':'systemd_user','darwin':'launch_agent','win32':'scheduled_task'}[sys.platform]
            services={k:{'manager':manager,'name':'minecraft-unused-fixture-'+k+('.service' if sys.platform=='linux' else ''),'definition_path':None} for k in ('body','controller')}
            initialize_config(driver,config,{'version':1,'roots':{'home':str(home),'state':str(state)},
                'locks':{'installation':str(state/'installation.lock')},'services':services})
            cfg={'home':str(home),'state':str(state),'native_platform':{'version':1,'driver':str(driver),
                'config':str(config),'library':str(lib),'library_sha256':hashlib.sha256(lib.read_bytes()).hexdigest()}}
            with Session(driver,config) as contender:
                with native_scope(cfg) as native,installation_lock(state/'installation.lock'):
                    for effect in ('direct','journal'):
                        with self.assertRaises(Busy):
                            with contender.lock('installation'):self.fail('contender entered')
                        if effect=='direct':(state/'direct.txt').write_text('original Python caller')
                        else:durable_write(state/'transactions/original.json',{'phase':'intent','unknown':'retained'})
                    self.assertEqual(native.process_identity(os.getpid())['pid'],os.getpid())
                with contender.lock('installation'):
                    self.assertEqual((state/'direct.txt').read_text(),'original Python caller')
                    self.assertEqual(json.loads((state/'transactions/original.json').read_bytes()),{'phase':'intent','unknown':'retained'})

if __name__=='__main__':unittest.main()
