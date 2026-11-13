import contextlib
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from installation_guard import ContinuityError,owner_io
from installation_native import NativeIO
from installation_native_bootstrap import setup
from installation_native_package import create_payload_file
from test_native_service_evidence import service


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.bundle=self.base/'bundle';self.bundle.mkdir()
        self.root=self.base/'new-home';self.calls=[];self.sessions=[];self.fail_role=None
        commands={'python':'python/bin/python3','node':'node/bin/node','task_helper':'task-helper/agent-runtime',
                  'native_driver':'native/driver','native_library':'native/library'}
        payload={**{v:k.encode() for k,v in commands.items()},'app/native_entry.py':b'entry',
                 'app/body.cjs':b'body','app/package.json':b'{}'}
        files={}
        for name,data in payload.items():
            p=self.bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            files[name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
        self.manifest={'schema':1,'files':files,'commands':commands,'target':'linux-arm64','source_clean':True,'source_commit':'a'*40,
          'native_platform':{'abi':1,'repository':'microsoft/amplifier-constellation',
            'driver_sha256':files['native/driver']['sha256'],'library_sha256':files['native/library']['sha256']}}
        self.save_manifest()
        self.engine=self.base/'engine';self.engine.write_bytes(b'not executed')
        self.plan={'schema':1,'root':str(self.root),'game':{'token':'private','control_port':1234},
                   'endpoint':{'command':[str(self.engine)],'cwd':str(self.base)}}
        owner=self
        class Session:
            def __init__(self,*args):
                config=args[-1];self.bootstrap_cli=len(args)==2
                self.config=json.loads(Path(config).read_bytes());self.locked=False;owner.sessions.append(self)
            def describe(self):return {'private_data_read':1,'private_data_publication':1,'operations':['storage.read_data','storage.write_data']}
            def private_write_data(self,root,rel,data):return self.private_write(root,rel,data)
            def __enter__(self):return self
            def __exit__(self,*args):owner.calls.append(('close',self.locked))
            @contextlib.contextmanager
            def lock(self,name):
                self.locked=True
                try:yield
                finally:self.locked=False
            def path(self,root,rel):
                assert self.locked or self.bootstrap_cli
                p=Path(self.config['roots'][root])/rel
                assert '..' not in Path(rel).parts
                return p
            def private_write(self,root,rel,data,create_only=False):
                p=self.path(root,rel)
                with p.open('xb' if create_only else 'wb') as stream:stream.write(data)
            def private_dir(self,root,rel):self.path(root,rel).mkdir(exist_ok=True)
            def service_register(self,role):
                owner.calls.append(('register',role))
                if owner.fail_role==role:raise RuntimeError('unknown after dispatch')
                return {'created':True}
            def service_snapshot(self,role):return service(active=False,enabled=False)
        def initialize_root(driver,path):
            owner.calls.append(('root',str(path)))
            if path.exists():return {'created':False}
            path.mkdir();return {'created':True}
        def initialize_config(driver,path,value):
            owner.calls.append(('config',str(path)))
            with path.open('xb') as stream:stream.write(json.dumps(value).encode())
        self.module=types.SimpleNamespace(Session=Session,NativeSession=Session,initialize_root=initialize_root,initialize_config=initialize_config)
    def save_manifest(self):(self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
    def run_setup(self):
        with patch.dict(sys.modules,{'constellation_native':self.module}),patch('installation_native_bootstrap.target',return_value='linux-arm64'):
            return setup(self.bundle,self.plan)
    def test_fresh_only_fixed_profiles_stopped_no_session_no_enrollment(self):
        result=self.run_setup();self.assertEqual(result['phase'],'registered_stopped')
        self.assertEqual([c for c in self.calls if c[0]=='register'],[('register','body'),('register','controller')])
        self.assertFalse(result['enrolled']);self.assertFalse(result['start_requested'])
        self.assertFalse((self.root/'home/session.json').exists())
        for root,names in {'home':('installation-updates','installation-connections'),
                'state':('transactions','connections','provider-receipts','native-source-receipts','artifact-receipts')}.items():
            for name in names:self.assertTrue((self.root/root/name).is_dir())
        self.assertEqual(json.loads((self.root/'home/endpoint.json').read_text()),self.plan['endpoint'])
        fixed=json.loads((self.root/'state/native.json').read_text())
        self.assertEqual((self.root/'state/native/driver').read_bytes(),b'native_driver')
        self.assertEqual((self.root/'state/native/library').read_bytes(),b'native_library')
        self.assertEqual(fixed['registrations']['body']['executable'],str(self.root/'state/native/driver'))
        self.assertTrue(all(x['autostart'] is False for x in fixed['registrations'].values()))
        self.assertTrue(all(c[1] is False for c in self.calls if c[0]=='close'))
        before=len(self.calls)
        with self.assertRaisesRegex(ContinuityError,'never reuses'):self.run_setup()
        self.assertEqual(len(self.calls),before)
    def test_unknown_registration_retains_intent_and_never_retries(self):
        self.fail_role='controller'
        with self.assertRaisesRegex(RuntimeError,'unknown after'):self.run_setup()
        receipt=self.root/'state/setup.json';before=receipt.read_bytes();state=json.loads(before)
        self.assertEqual(state['services']['body']['phase'],'registered_stopped')
        self.assertEqual(state['services']['controller']['phase'],'dispatch_pending')
        with self.assertRaises(ContinuityError):self.run_setup()
        self.assertEqual(receipt.read_bytes(),before)
        self.assertEqual(len([c for c in self.calls if c==('register','controller')]),1)
    def test_interrupted_private_copy_retains_unpublished_root_without_retry(self):
        with patch('installation_native_bootstrap.fill_created_payload_file',side_effect=OSError('copy interrupted')):
            with self.assertRaisesRegex(OSError,'copy interrupted'):self.run_setup()
        self.assertTrue(all(s.bootstrap_cli for s in self.sessions))
        self.assertFalse(any(c[0]=='register' for c in self.calls))
        self.assertFalse((self.root/'state/owner.json').exists())
        before=(self.root/'state/setup.json').read_bytes();count=len(self.calls)
        with self.assertRaises(ContinuityError):self.run_setup()
        self.assertEqual((self.root/'state/setup.json').read_bytes(),before)
        self.assertEqual(len(self.calls),count)
    def test_existing_empty_root_is_not_unused_proof(self):
        self.root.mkdir()
        with self.assertRaises(ContinuityError):self.run_setup()
        self.assertEqual(self.calls,[]);self.assertEqual(list(self.root.iterdir()),[])
    def test_package_drift_refuses_before_bootstrap(self):
        (self.bundle/'native/library').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_setup()
        self.assertEqual(self.calls,[]);self.assertFalse(self.root.exists())
    def test_missing_library_pair_refuses_without_mutation(self):
        self.manifest['native_platform'].pop('abi');self.save_manifest()
        with self.assertRaisesRegex(ValueError,'pair required'):self.run_setup()
        self.assertEqual(self.calls,[])
    def test_invalid_plan_refuses_without_mutation(self):
        self.plan['endpoint']['command']=['relative']
        with self.assertRaises(ValueError):self.run_setup()
        self.assertEqual(self.calls,[])
    def test_large_private_file_seed_is_create_only_before_streaming(self):
        # Payload bytes do not travel through the bounded JSON frame. Ownership
        # is established on an empty file before the direct caller writes.
        state=self.base/'state';home=self.base/'home';state.mkdir();home.mkdir()
        config=self.base/'native.json';config.write_text(json.dumps({'roots':{'state':str(state),'home':str(home)}}))
        session=self.module.NativeSession(None,None,config)
        cfg={'state':str(state),'home':str(home)};destination=state/'large'
        with session.lock('installation'),owner_io(NativeIO(cfg,session)):
            data=b'a'*(17*1024*1024);create_payload_file(destination,io.BytesIO(data),0o755)
            self.assertEqual(destination.read_bytes(),data)
            with self.assertRaises(FileExistsError):create_payload_file(destination,io.BytesIO(b'overwrite'))
        self.assertEqual(destination.stat().st_size,len(data))

    def test_small_payload_uses_one_protected_create_with_complete_bytes(self):
        state=self.base/'state';home=self.base/'home';state.mkdir();home.mkdir()
        config=self.base/'native.json';config.write_text(json.dumps({'roots':{'state':str(state),'home':str(home)}}))
        session=self.module.NativeSession(None,None,config);cfg={'state':str(state),'home':str(home)}
        for size in (0,13,65536):
            data=b'x'*size;destination=state/str(size)
            with session.lock('installation'),owner_io(NativeIO(cfg,session)),patch.object(session,'private_write',wraps=session.private_write) as write:
                create_payload_file(destination,io.BytesIO(data),0o755)
                write.assert_called_once_with('state',str(size),data,create_only=True)
                self.assertEqual(destination.read_bytes(),data)
                with self.assertRaises(FileExistsError):create_payload_file(destination,io.BytesIO(b'replace'))
                self.assertEqual(destination.read_bytes(),data)

    def test_short_reads_do_not_truncate_either_payload_route(self):
        class Short(io.BytesIO):
            def read(self,n=-1):return super().read(min(n,731))
        state=self.base/'state';home=self.base/'home';state.mkdir();home.mkdir()
        config=self.base/'native.json';config.write_text(json.dumps({'roots':{'state':str(state),'home':str(home)}}))
        session=self.module.NativeSession(None,None,config);cfg={'state':str(state),'home':str(home)}
        with session.lock('installation'),owner_io(NativeIO(cfg,session)):
            for size in (65536,65537,1048577):
                data=bytes(range(251))*(size//251)+b'z'*(size%251)
                destination=state/str(size);create_payload_file(destination,Short(data))
                self.assertEqual(destination.read_bytes(),data)

    def test_small_create_unknown_never_falls_back_to_direct_write(self):
        state=self.base/'state';home=self.base/'home';state.mkdir();home.mkdir()
        config=self.base/'native.json';config.write_text(json.dumps({'roots':{'state':str(state),'home':str(home)}}))
        session=self.module.NativeSession(None,None,config);cfg={'state':str(state),'home':str(home)}
        with session.lock('installation'),owner_io(NativeIO(cfg,session)),patch.object(session,'private_write',side_effect=RuntimeError('unknown publication')) as write,patch('installation_native_package.fill_created_payload_file') as fill:
            with self.assertRaisesRegex(RuntimeError,'unknown publication'):create_payload_file(state/'file',io.BytesIO(b'payload'))
            write.assert_called_once_with('state','file',b'payload',create_only=True)
            fill.assert_not_called()

if __name__=='__main__':unittest.main()
