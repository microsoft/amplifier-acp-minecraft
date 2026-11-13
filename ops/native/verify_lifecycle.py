"""Actual target-OS package + driver + SDK lifecycle using only disposable services.
Shared test helpers provide fixture ACLs/cleanup; production setup uses the driver.
"""
import hashlib,json,os,pathlib,shutil,socket,subprocess,sys,tempfile,time,uuid
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--source',type=pathlib.Path,required=True);parser.add_argument('--bundle',type=pathlib.Path,required=True);parser.add_argument('--shared',type=pathlib.Path,required=True);parser.add_argument('--driver',type=pathlib.Path,required=True);parser.add_argument('--receipt',type=pathlib.Path,required=True);args=parser.parse_args()
SOURCE=args.source.resolve();BUNDLE=args.bundle.resolve();SHARED=args.shared.resolve();DRIVER=args.driver.resolve()
manifest=json.loads((BUNDLE/'manifest.json').read_text())
LIBRARY=BUNDLE/manifest['commands']['native_library']
sys.path[:0]=[str(BUNDLE/'app'),str(SHARED/'support/python'),str(SHARED/'tests/native_python')]
os.environ['CONSTELLATION_NATIVE_DRIVER']=str(DRIVER)
from test_driver import protect as shared_protect
# Explicit script directory is needed with the bundled interpreter -I flag.
sys.path.insert(0,str(SOURCE/'ops/native'))
from fixture_security import protect_fixture_path,fixture_application_identities
from test_service import NativeServiceApplicationTests
from constellation_native import Session, NativeSession, Refused, initialize_root, initialize_config
from installation_native import NativeIO,NativeInstallation,validate_driver_mapping,connection_backend
from installation_guard import owner_io,installation_lock,durable_write,read,service_active,service_stopped
from installation_participant import Participant
from installation_connection import Connection
from installation_native_exchange import NativeExchange
from installation_source_provider import Provider,fingerprint,verify_sdk
from installation_enrollment import registration
from installation_guard import digest

fixture_root=None

def protect(path):
    if fixture_root is None:raise RuntimeError('Disposable root not initialized')
    protect_fixture_path(path,fixture_root,shared_protect)

def initial(path,value):
    path.write_text(json.dumps(value),encoding='utf-8');protect(path)

def wait_services(backend):
    until=time.monotonic()+40
    while time.monotonic()<until:
        try:
            before=backend.capture()
            if before['status_idle'] and all(service_active(v) for v in before['services'].values()):return before
        except Exception:pass
        time.sleep(.1)
    raise RuntimeError('Disposable native services did not become observable')

fixture=r'''
import argparse,http.server,json,pathlib,sys,time
p=argparse.ArgumentParser();p.add_argument('--role');p.add_argument('--home');p.add_argument('--driver');p.add_argument('--driver-config');p.add_argument('--shared');a=p.parse_args()
home=pathlib.Path(a.home);cfg=json.loads((home/'config.json').read_text())
if a.role=='body':
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   if self.headers.get('Authorization')!='Bearer '+cfg['token']:self.send_error(403);return
   data={'version':1,'task':json.loads((home/'workshop.json').read_text())['task'],
    'ready':True,'busy':False,'turn_active':False,'window_open':False,'action_sequence':None,
    'action_lease':{'version':1,'lease_id':None,'expires_at':0,'renewable':False},
    'inventory':{'slots':[{'name':'pickaxe','damage':48}],'cursor':None},'position':{'x':1,'y':64,'z':3}}
   self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
 http.server.HTTPServer(('127.0.0.1',cfg['control_port']),Handler).serve_forever()
else:
 sys.path.insert(0,a.shared)
 from constellation_native import Session
 with Session(a.driver,a.driver_config) as driver:
  me=driver.process_identity(__import__('os').getpid())
  while True:
   gate=home/'installation-updates/gate.json'
   if gate.exists():
    g=json.loads(gate.read_text());ack={'transaction_id':g['transaction_id'],**me}
    dest=home/'installation-updates/controller-idle.json'
    if not dest.exists() or json.loads(dest.read_text())!=ack:
     driver.private_write('home','installation-updates/controller-idle.json',json.dumps(ack).encode())
   time.sleep(.05)
'''
class FixtureCleanup(NativeServiceApplicationTests):
 def __init__(self,service):
  super().__init__();self.fixture_service=service
 def receipt_identities(self,receipt):
  return fixture_application_identities(receipt,self.fixture_service)

if os.name=='nt':
 cleanup_fixture=pathlib.Path(os.environ.get('NATIVE_SERVICE_FIXTURE',str(SHARED/'crates/native-platform/target/debug/examples/windows_service_fixture.exe')))
 if not cleanup_fixture.is_file():raise RuntimeError('Build the shared disposable Windows cleanup fixture first')
 os.environ['NATIVE_SERVICE_FIXTURE']=str(cleanup_fixture)
 os.environ['CONSTELLATION_INSTALLATION_SMOKE']='1'

report={'source':manifest['source_commit'],'bundle_target':manifest['target'],
 'shared_source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=SHARED,text=True).strip(),
 'driver_sha256':hashlib.sha256(DRIVER.read_bytes()).hexdigest(),'library_sha256':hashlib.sha256(LIBRARY.read_bytes()).hexdigest(),'session_boundary':'NativeSession ABI1',
 'production_operations':False,'model_prompts':0,'actual_os':sys.platform,'cycles':[],
 'cleanup_fixture_sha256':hashlib.sha256(cleanup_fixture.read_bytes()).hexdigest() if os.name=='nt' else None,
 'fixture_protection':{'shared_owner_and_dacl':True,'domain_os_permission_commands':False,'scope':'Synthetic package/input files only; initial roots and driver config use production bootstrap'}}
units=[];dispatched=[];temp=None
try:
 temp=tempfile.TemporaryDirectory(prefix='minecraft-native-domain-');root=pathlib.Path(temp.name).resolve()/'installation';fixture_root=root
 home=root/'game';state=root/'state'
 report['bootstrap']={'roots':{}}
 for directory in (root,home,state):
  created=initialize_root(DRIVER,directory)
  assert created['created'] is True and pathlib.Path(created['path'])==directory,created
  existing=initialize_root(DRIVER,directory)
  assert existing['created'] is False,existing
  report['bootstrap']['roots'][directory.name]={'created':created,'validated_existing':existing}
 # Existing private directories alone are not unused-slot proof. This test owns
 # the fresh temporary parent and the three newly-created empty children above.
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 cfg={'home':str(home),'state':str(state),'session_verification_seconds':12,
  'native_platform':{'version':1,'data_journals':1,'library':str(LIBRARY),'library_sha256':hashlib.sha256(LIBRARY.read_bytes()).hexdigest(),'python':sys.executable,'services':{'body':'body','controller':'controller'},'driver':str(DRIVER),'config':str(root/'driver.json')},
  'service_connection':{'id':'minecraft-native-fixture','label':'Native fixture','revision':'a'*64,'context_provider_ids':['minecraft:native-fixture']}}
 task={'id':'original','status':'budget_exhausted','turns':8}
 initial(home/'workshop.json',{'task':task,'turn':None,'inbox':[],'unknown_receipts':['preserved']})
 gamecfg={'control_port':port,'token':'disposable-fixture-only'};initial(home/'config.json',gamecfg)
 (home/'app').mkdir();protect(home/'app')
 for item in [*(BUNDLE/'app').glob('*.py'),BUNDLE/'app/requirements.txt']:
  shutil.copyfile(item,home/'app'/item.name);protect(home/'app'/item.name)
 peer=root/'peer.py';shutil.copyfile(SOURCE/'tests/session_probe_fixture.py',peer);log=root/'acp.jsonl'
 endpoint={'command':[sys.executable,str(peer)],'cwd':str(root),'env':{'PROBE_LOG':str(log)}}
 effective={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':f'http://127.0.0.1:{port}/mcp',
   'headers':[{'name':'Authorization','value':'Bearer disposable-fixture-only'}]}]}
 initial(home/'endpoint.json',endpoint)
 initial(home/'session.json',{'session':'original-fixture-session','binding':hashlib.sha256(json.dumps(effective,sort_keys=True).encode()).hexdigest()})
 shutil.copytree(BUNDLE/'python',home/'venv',symlinks=True);protect(home/'venv')
 (home/'venv/original.txt').write_text('retained environment')
 (state/'stages').mkdir();protect(state/'stages')
 candidate=state/'stages'/str(uuid.uuid4());candidate.mkdir();protect(candidate)
 shutil.copytree(home/'app',candidate/'app');protect(candidate/'app')
 (candidate/'app/candidate-marker.txt').write_text('reviewed candidate source')
 shutil.copytree(BUNDLE/'python',candidate/'venv',symlinks=True);protect(candidate/'venv')
 (candidate/'venv/candidate.txt').write_text('reviewed candidate environment')
 targets={k:{'root':'state','path':(candidate/k).relative_to(state).as_posix()} for k in ('app','venv')}
 environment_python='python.exe' if os.name=='nt' else 'bin/python3'
 cfg['native_platform'].update(python=str(home/'venv'/environment_python),environment_python=environment_python)
 cfg.update(app=str(home/'app'),venv=str(home/'venv'),python=sys.executable,node=str(BUNDLE/manifest['commands']['node']),npm_cli=str(BUNDLE/'app/package.json'),channel='latest-passing-development',required_checks=['disposable-boundary'])
 helpers=home/'task-helpers';helpers.mkdir();protect(helpers)
 helper=helpers/('agent-runtime.exe' if os.name=='nt' else 'agent-runtime')
 shutil.copy2(BUNDLE/manifest['commands']['task_helper'],helper);protect(helper)
 if os.name!='nt':helper.chmod(0o700)
 shared_plans=root/'shared'/'plans';shared_plans.mkdir(parents=True);protect(shared_plans.parent);protect(shared_plans)
 initial(shared_plans.parent/'state.json',{'state':'succeeded','transaction':None})
 cfg.update(task_helper=str(helper),shared_plans=str(shared_plans))
 initial(home/'app-source.json',{'revision':'a'*40,'fixture':True})
 original={p.name:p.read_bytes() for p in home.iterdir() if p.is_file() and p.name!='app-source.json'}
 original_source=read(home/'app-source.json')
 script=root/'fixture.py';script.write_text(fixture);protect(script)
 drivercfg=root/'driver.json';ownercfg=root/'owner.json';ownercfg.write_text(json.dumps(cfg));protect(ownercfg)
 wrapper=root/'probe-entry.py';wrapper.write_text('import sys,runpy\nsys.path[:0]='+repr([str(BUNDLE/'app'),str(SHARED/'support/python')])+'\nrunpy.run_module("connection_session_job",run_name="__main__")\n');protect(wrapper)
 service_map={};registrations={};applications={}
 for role in ('body','controller'):
  name='minecraft-native-disposable-'+uuid.uuid4().hex+'-'+role
  definition=None
  if sys.platform=='linux':
   name+='.service';manager='systemd_user';definition=pathlib.Path.home()/'.config/systemd/user'/name
  elif sys.platform=='darwin':
   manager='launch_agent';definition=pathlib.Path.home()/'Library/LaunchAgents'/(name+'.plist')
  else:
   manager='scheduled_task';name='constellation-driver-test-'+uuid.uuid4().hex
  if definition:definition.parent.mkdir(parents=True,exist_ok=True)
  units.append((name,definition))
  argv=[str(script),'--role',role,'--home',str(home),'--driver',str(DRIVER),'--driver-config',str(drivercfg),'--shared',str(SHARED/'support/python')]
  service_map[role]={'manager':manager,'name':name,'definition_path':str(definition) if definition else None}
  registrations[role]={'executable':str(DRIVER),'args':['--config',str(drivercfg),'service-run','--service',role],
     'cwd':str(root),'description':'Disposable Minecraft lifecycle '+role,'autostart':False}
  applications[role]={'executable':sys.executable,'args':argv,'cwd':str(root),'identity_path':str(state/(role+'-identity.json'))}
 data={'version':1,'roots':{'home':str(home),'state':str(state)},'locks':{'installation':str(state/'installation.lock')},'services':service_map,'registrations':registrations,'service_applications':applications,'commands':{'session_endpoint':{'executable':endpoint['command'][0],'args':endpoint['command'][1:],'cwd':endpoint['cwd'],'timeout_seconds':200},'session_probe':{'executable':cfg['native_platform']['python'],'args':[str(wrapper),'--home',str(home),'--result','{result}','--native-owner-config',str(ownercfg)],'cwd':str(root),'timeout_seconds':200,'result_root':'state'}}}
 data['exchanges']={key:{'lock':'installation','profile':{'current':str(home/key),'roots':{'state':str(state)}}} for key in ('app','venv')}
 published=initialize_config(DRIVER,drivercfg,data)
 assert published['created'] is True,published
 original_config=drivercfg.read_bytes()
 existing=initialize_config(DRIVER,drivercfg,data)
 assert existing['created'] is False and drivercfg.read_bytes()==original_config,existing
 changed=json.loads(json.dumps(data));changed['registrations']['body']['description']+=' changed'
 try:initialize_config(DRIVER,drivercfg,changed)
 except Refused:pass
 else:raise AssertionError('Bootstrap replaced an existing different owner config')
 assert drivercfg.read_bytes()==original_config
 report['bootstrap'].update(config=published,validated_existing_config=existing,changed_config_refused=True)
 validate_driver_mapping(cfg,drivercfg)
 preflight=subprocess.run([str(DRIVER),'--config',str(drivercfg),'serve'],
     input=json.dumps({'version':1,'id':'read-only-preflight','op':'describe'})+'\n',capture_output=True,text=True,timeout=20)
 report['driver_preflight']={'returncode':preflight.returncode,'stdout':preflight.stdout,'stderr':preflight.stderr}
 if preflight.returncode:raise RuntimeError('Native driver configuration failed: '+preflight.stderr)
 enrollment=registration(ownercfg,BUNDLE/'app',pathlib.Path(sys.executable))
 status_command=enrollment['components'][0]['commands']['status']
 owner_status=subprocess.run(status_command,capture_output=True,text=True,timeout=30)
 report['native_owner_registration']={'delta':enrollment,'status_returncode':owner_status.returncode,'status_stdout':owner_status.stdout,'status_stderr':owner_status.stderr}
 assert owner_status.returncode==0,report['native_owner_registration']
 assert json.loads(owner_status.stdout)['version']=='a'*40
 with NativeSession(LIBRARY,DRIVER,drivercfg) as session:
  io=NativeIO(cfg,session);backend=NativeInstallation(cfg,session)
  with owner_io(io),installation_lock(state/'installation.lock'):
   io.prepare_data_journal_directories()
   for kind in ('body','controller'):
    dispatched.append((*units[0 if kind=='body' else 1],drivercfg,state/(kind+'-identity.json'),kind))
    assert session.service_register(kind)=={'created':True}
    stopped=session.service_snapshot(kind);assert service_stopped(stopped),stopped
    assert session.service_register(kind)=={'created':False}
    assert session.service_snapshot(kind)==stopped
    session.service_action(kind,'start',stopped)
   before=wait_services(backend);report['fresh_no_start_registration']=True
   for components in (['instance'],['minecraft']):
    env={'id':str(uuid.uuid4()),'participant':'minecraft','plan':{'schema':1,'transaction_id':str(uuid.uuid4()),'operation':'apply','components':components}}
    p=Participant(cfg,env,backend)
    for _ in range(200):
     if p.prepare()['ready']:break
     time.sleep(.1)
    else:raise RuntimeError('Actual native prepare did not settle')
    if components==['minecraft']:
     provider=Provider(cfg,backend=backend)
     marker=read(home/'app-source.json')
     frozen={'revision':manifest['source_commit'],'sdk':verify_sdk(candidate/'venv',candidate/'app'),
         'fingerprints':{k:fingerprint(candidate/k) for k in ('app','venv')},
         'python_sha256':hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest()}
     initial(candidate/'manifest.json',frozen)
     plan={'stage':str(candidate),'config_hash':digest(cfg),'manifest_hash':digest(frozen),'version':manifest['source_commit'],
         'previous':'a'*40,'source_marker':marker,'source_marker_version':2,
         'before':{k:fingerprint(home/k) for k in ('app','venv')}}
     envelope={'id':env['id'],'component':'minecraft','plan':plan}
     assert provider.apply(envelope,env['plan']['transaction_id'])['verified']
     assert (home/'app/candidate-marker.txt').read_text()=='reviewed candidate source'
     assert provider.apply(envelope,env['plan']['transaction_id'])['verified']
     # Verify actual candidate SDK before restoring source, without opening a
     # conversation or accepting any model work.
     assert backend.session(12)['saved_session_loaded']
     assert provider.rollback(envelope,env['plan']['transaction_id'])['verified']
     assert (home/'venv/original.txt').read_text()=='retained environment'
     assert not (home/'app/candidate-marker.txt').exists()
     assert provider.rollback(envelope,env['plan']['transaction_id'])['verified']
     report['native_source_exchange']=read(state/'native-source-receipts'/(env['id']+'.json'))
    assert p.verify('applied')['verified'];assert p.restore('applied')['restored']
    terminal=read(p.path);assert Participant(cfg,env,backend).restore('applied')['restored']
    assert {q.name:q.read_bytes() for q in home.iterdir() if q.is_file() and q.name!='app-source.json'}==original
    assert read(home/'app-source.json')==original_source
    report['cycles'].append({'components':components,'transaction':env['plan']['transaction_id'],'receipt':terminal,'after':backend.capture()})
   native_connection=connection_backend(cfg,session);request=str(uuid.uuid4())
   def conn(action='status'):
    return Connection(cfg,{'schema':1,'connection_id':'minecraft-native-fixture','revision':'a'*64,'action':action,'request_id':request},native_connection)
   conn('disconnect').run();quiescence_seen=False
   for _ in range(200):
    result=conn().run();quiescence_seen|=result.get('context_quiesced',False)
    if result['settled']:break
    time.sleep(.1)
   assert result['state']=='disconnected' and result['settled'] and quiescence_seen,result
   disconnected=read(conn().path);request=str(uuid.uuid4());conn('connect').run();readiness_seen=False
   for _ in range(250):
    result=conn().run();readiness_seen|=result.get('context_ready',False)
    if result['settled']:break
    time.sleep(.1)
   assert result['state']=='connected' and result['settled'] and readiness_seen,result
   assert conn().run()==result
   report['connection']={'disconnected':disconnected,'connected':read(conn().path),'quiescence_seen':quiescence_seen,'readiness_seen':readiness_seen}
   assert {q.name:q.read_bytes() for q in home.iterdir() if q.is_file() and q.name!='app-source.json'}==original
   assert read(home/'app-source.json')==original_source
  report['acp_events']=[json.loads(line) for line in log.read_text().splitlines()]
  assert report['acp_events']==[{'action':'initialize'},{'action':'load','session':'original-fixture-session'}]*4
 report['passed']=True
finally:
 cleanup_errors=[]
 for name,definition,config,identity,kind in dispatched:
  try:FixtureCleanup(kind).cleanup(name,definition,config,identity)
  except Exception as error:cleanup_errors.append({'service':name,'error':repr(error)})
 report['cleanup_errors']=cleanup_errors
 if temp:temp.cleanup()
 report['disposable_units_removed']=not cleanup_errors
 args.receipt.write_text(json.dumps(report,indent=2)+'\n')
 if cleanup_errors:raise RuntimeError('Disposable native service cleanup failed; see retained receipt')
print(json.dumps({'passed':report.get('passed',False),'target':manifest['target'],'cycles':len(report['cycles']),'original_session_loads':len(report.get('acp_events',[]))//2}))
