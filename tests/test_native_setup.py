import hashlib,json,tempfile,unittest,contextlib
from pathlib import Path
from installation_native_setup import profiles,register_no_start
from installation_guard import ContinuityError
from test_native_service_evidence import service


class SetupTests(unittest.TestCase):
    def test_fixed_profiles_preserve_endpoint_and_use_isolated_same_process_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);home=root/'home';state=root/'state';bundle=root/'bundle'
            home.mkdir();state.mkdir();bundle.mkdir();(home/'app').mkdir();(home/'app/native_entry.py').write_text('entry')
            endpoint={'command':[str(root/'engine'),'--stdio'],'cwd':str(root),'env':{'SECRET_REFERENCE':'retained'}}
            for name,value in [('config.json',{'control_port':1234,'token':'fixture'}),('endpoint.json',endpoint)]:
                (home/name).write_text(json.dumps(value))
            commands={k:k for k in ['native_driver','python','node']};files={}
            for name in commands:
                (bundle/name).write_bytes(name.encode());files[name]={'sha256':hashlib.sha256(name.encode()).hexdigest()}
            manifest={'commands':commands,'files':files,'native_platform':{'repository':'microsoft/amplifier-constellation','driver_sha256':files['native_driver']['sha256']}}
            (bundle/'manifest.json').write_text(json.dumps(manifest))
            cfg={'home':str(home),'state':str(state),'native_platform':{'driver':str(bundle/'native_driver'),'python':str(bundle/'python'),'config':str(state/'driver.json')}}
            original={p.name:p.read_bytes() for p in home.iterdir() if p.is_file()}
            services={k:{'manager':'scheduled_task','name':'Minecraft-'+k} for k in ['body','controller']}
            result=profiles(cfg,state/'owner.json',bundle,services)
            self.assertTrue(all(p['autostart'] is False for p in result['registrations'].values()))
            self.assertEqual(result['service_applications']['controller']['args'][:3],['-I',str(home/'app/native_entry.py'),'controller'])
            self.assertEqual(result['commands']['session_endpoint']['args'],endpoint['command'][1:])
            self.assertNotIn('SECRET_REFERENCE',json.dumps(result));self.assertFalse((home/'session.json').exists())
            self.assertEqual({p.name:p.read_bytes() for p in home.iterdir() if p.is_file()},original)
            (bundle/'native_driver').write_bytes(b'changed')
            with self.assertRaises(ValueError):profiles(cfg,state/'owner.json',bundle,services)
    def test_register_does_not_start_or_unpause_existing_service(self):
        class Driver:
            def __init__(self):self.calls=[]
            def describe(self):return {'operations':['service.register','service.snapshot','process.identity']}
            @contextlib.contextmanager
            def lock(self,name):yield
            def service_register(self,name):self.calls.append(name);return {'created':name=='body'}
            def service_snapshot(self,name):return service(active=False,enabled=False)
        driver=Driver();result=register_no_start(driver,{'exact':True},{'exact':True})
        self.assertFalse(result['start_requested']);self.assertEqual(driver.calls,['body','controller'])
        with self.assertRaises(ContinuityError):register_no_start(driver,{'exact':True},{'exact':False})
        self.assertEqual(driver.calls,['body','controller'])

if __name__=='__main__':unittest.main()
