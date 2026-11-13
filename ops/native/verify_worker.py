"""Pinned actual Worker -> production participant -> packaged NativeSession.

Only external API and native service observations are fixture data. Real worker
transaction/admission, subprocess, locks, participant journals and gate ownership
execute. No OS service or engine/model/world call is permitted.
"""
import argparse,contextlib,hashlib,importlib.util,json,os,sys,tempfile,uuid
from pathlib import Path
from unittest.mock import patch

def load(spec):
 sys.path[:0]=[spec['facade'],spec['app'],str(Path(spec['source'])/'tests'),str(Path(spec['shared'])/'tests/native_python')]

def child(file,action):
 spec=json.loads(file.read_bytes());load(spec)
 from installation_native import NativeInstallation,native_scope
 from installation_guard import installation_lock
 from installation_participant import main
 from test_native_service_evidence import NativeFixture
 cfg=spec['cfg'];fixture=NativeFixture.__new__(NativeFixture)
 fixture.home=Path(cfg['home']);fixture.units=spec['units'];fixture.body=spec['body'];fixture.actions=[]
 original=NativeInstallation
 def factory(cfg,native):
  backend=original(cfg,native)
  backend.services=fixture.services;backend.capture=fixture.capture
  backend.action=lambda *a:(_ for _ in ()).throw(AssertionError('Forbidden domain service action'))
  return backend
 sys.argv=['installation_participant','--config',spec['owner'],action]
 try:
  with patch('installation_native.NativeInstallation',side_effect=factory):main()
 except Exception as error:
  with (file.parent/'child-errors.jsonl').open('a') as log:log.write(json.dumps({'action':action,'type':type(error).__name__,'message':str(error)})+'\n')
  raise

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--child',type=Path);parser.add_argument('--action')
 for n in ('bundle','source','shared','instance','receipt'):parser.add_argument('--'+n,type=Path)
 args=parser.parse_args()
 if args.child:return child(args.child,args.action)
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 from fixture_security import copy_fixture_driver
 bundle=args.bundle.resolve();source=args.source.resolve();shared=args.shared.resolve()
 import constellation_native
 spec={'app':str(bundle/'app'),'source':str(source),'shared':str(shared),'facade':str(Path(constellation_native.__file__).resolve().parents[1])};load(spec)
 from constellation_native import initialize_root,initialize_config,NativeSession
 from installation_native import native_scope,NativeIO
 from installation_guard import installation_lock,durable_write,owner_io
 from test_native_service_evidence import NativeFixture
 from test_driver import protect
 pin=json.loads((source/'ops/native/instance-worker-lock.json').read_bytes())
 path=args.instance.resolve()/pin['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==pin['sha256']
 module=importlib.util.spec_from_file_location('qualified_actual_worker',path);worker=importlib.util.module_from_spec(module);module.loader.exec_module(worker)
 manifest=json.loads((bundle/'manifest.json').read_bytes());input_driver=bundle/manifest['commands']['native_driver'];library=bundle/manifest['commands']['native_library'];results=[]
 for scenario in ('body-disabled','controller-disabled','owned-gate','foreign-gate'):
  driver=input_driver
  with tempfile.TemporaryDirectory(prefix='minecraft-worker-domain-') as tmp:
   base=Path(tmp).resolve();protect(base);home=base/'home';state=base/'state';wr=base/'worker'
   for p in (home,state,wr):initialize_root(driver,p)
   manager={'linux':'systemd_user','darwin':'launch_agent','win32':'scheduled_task'}[sys.platform]
   native_config=state/'native.json';owner=state/'owner.json'
   cfg={'home':str(home),'state':str(state),'native_platform':{'version':1,'data_journals':1,'driver':str(driver),'library':str(library),
     'library_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),'config':str(native_config),'python':sys.executable,'services':{'body':'body','controller':'controller'}}}
   initialize_config(driver,native_config,{'version':1,'roots':{'home':str(home),'state':str(state)},'locks':{'installation':str(state/'installation.lock')},
      'services':{k:{'manager':manager,'name':'unused-worker-fixture-'+k+('.service' if sys.platform=='linux' else ''),'definition_path':None} for k in ('body','controller')}})
   driver=copy_fixture_driver(driver,state,native_config);cfg['native_platform']['driver']=str(driver)
   with NativeSession(library,driver,native_config) as session,session.lock('installation'):
    io=NativeIO(cfg,session);io.prepare_data_journal_directories()
    # Seed the synthetic baseline through the actual protected writer as well;
    # the legacy POSIX fixture writer is not a Windows storage implementation.
    with owner_io(io):fixture=NativeFixture(home,manager)
   # Native service data is a named synthetic topology, not OS state proof.
   for index,v in enumerate(fixture.units.values()):
    v['application']={'status':'running','identity':{'pid':500+index,'generation':'original-child'},
       'supervisor':{'pid':400+index,'generation':'original-parent'},
       'manager_process':v['processes'][0],'profile_sha256':'a'*64}
   if scenario.endswith('disabled'):fixture.units[scenario.split('-')[0]].update(start_allowed=False,enabled=False)
   else:fixture.body.update(busy=True,turn_active=True)
   # Fixed fixture inputs only; actual participant writes use native storage.
   owner.write_text(json.dumps(cfg));protect(owner)
   for p in home.rglob('*'):protect(p)
   fixed=base/'fixture.json';fixed.write_text(json.dumps({**spec,'cfg':cfg,'owner':str(owner),'units':fixture.units,'body':fixture.body}));protect(fixed)
   saved={p.name:p.read_bytes() for p in home.iterdir() if p.is_file()}
   caller=worker.Worker.__new__(worker.Worker);caller.root=wr;caller.file=wr/'state.json';caller.state={'state':'idle','enrolled_at':0}
   command=[sys.executable,'-I',str(Path(__file__).resolve()),'--child',str(fixed)]
   participant={'id':'minecraft','components':['instance'],'commands':{a:command+['--action',a] for a in ('prepare','verify','restore')}}
   caller.c={'components':[{'id':'instance','restart_scope':{'instance':True,'services':[],'slack_homes':[]}}],'participants':[participant]}
   reports=[];allowed_calls=[]
   caller.report=lambda **kw:reports.append(kw) or {'active_prompts':0}
   gate=home/'installation-updates/gate.json';foreign={'version':1,'transaction_id':str(uuid.uuid4()),'closed':True}
   def allowed(*a):
    allowed_calls.append(True)
    if len(allowed_calls)>1:
     if scenario=='foreign-gate':
      with native_scope(cfg),installation_lock(state/'installation.lock'):durable_write(gate,foreign)
     raise ValueError('bounded fixture policy cancellation')
   caller.allowed=allowed
   @contextlib.contextmanager
   def forbidden_drain(*a,**kw):raise AssertionError('Shared drain entered before domain admission');yield
   caller.drained=forbidden_drain
   caller.control=lambda *a:(_ for _ in ()).throw(AssertionError('Shared service dispatch'))
   plan={'id':str(uuid.uuid4()),'created_at':1,'components':[{'id':'instance','available':True}]}
   try:
    with worker.single_worker(wr):caller.transaction_apply(plan,{'revision':1})
   except (RuntimeError,ValueError) as error:failure=str(error)
   else:raise AssertionError('Expected bounded refusal/cancellation')
   assert not any(x.get('drain') is True for x in reports)
   assert {p.name:p.read_bytes() for p in home.iterdir() if p.is_file()}==saved
   if scenario.endswith('disabled'):
    failures=[json.loads(line) for line in (base/'child-errors.jsonl').read_text().splitlines()]
    assert any(x['action']=='prepare' and x['type']=='NotIdle' and 'masked, disabled' in x['message'] for x in failures),failures
    assert not gate.exists() and not (state/'active.json').exists()
    assert not list((state/'transactions').glob('*.json'))
   elif scenario=='owned-gate':assert not gate.exists()
   else:assert json.loads(gate.read_bytes())==foreign and caller.state['state']=='recovery_required'
   results.append({'case':scenario,'no_shared_drain':True,'original_files_unchanged':True,'only_owned_gate_cleanup':True,
                   'worker_terminal':caller.state['state'],'native_observations':'synthetic named topology'})
 args.receipt.write_text(json.dumps({'source':manifest['source_commit'],'target':manifest['target'],'worker':pin,'cases':results,
       'scope':__doc__,'production_operations':False},indent=2)+'\n')
 print('PASS',len(results),'actual Worker/participant/NativeSession cases')
if __name__=='__main__':main()
