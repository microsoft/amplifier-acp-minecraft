"""Actual target-OS package + driver + SDK lifecycle using only disposable services.
Shared test helpers provide fixture ACLs/cleanup; production setup uses the driver.
"""
import hashlib,json,os,pathlib,shutil,socket,subprocess,sys,tempfile,time,uuid
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--source',type=pathlib.Path,required=True);parser.add_argument('--bundle',type=pathlib.Path,required=True);parser.add_argument('--shared',type=pathlib.Path,required=True);parser.add_argument('--driver',type=pathlib.Path,required=True);parser.add_argument('--receipt',type=pathlib.Path,required=True);args=parser.parse_args()
SOURCE=args.source.resolve();BUNDLE=args.bundle.resolve();SHARED=args.shared.resolve();DRIVER=args.driver.resolve()
manifest=json.loads((BUNDLE/'manifest.json').read_text())
sys.path[:0]=[str(BUNDLE/'app'),str(SHARED/'support/python'),str(SHARED/'tests/native_python')]
os.environ['CONSTELLATION_NATIVE_DRIVER']=str(DRIVER)
from test_driver import protect
from test_service import NativeServiceApplicationTests
from constellation_native import Session
from installation_native import NativeIO,NativeInstallation,validate_driver_mapping,connection_backend
from installation_guard import owner_io,installation_lock,durable_write,read,service_active,service_stopped
from installation_participant import Participant
from installation_connection import Connection
from installation_native_exchange import NativeExchange

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
report={'source':manifest['source_commit'],'bundle_target':manifest['target'],
 'shared_source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=SHARED,text=True).strip(),
 'driver_sha256':hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
 'production_operations':False,'model_prompts':0,'actual_os':sys.platform,'cycles':[]}
units=[];dispatched=[];temp=None
try:
 temp=tempfile.TemporaryDirectory(prefix='minecraft-native-domain-');root=pathlib.Path(temp.name).resolve();protect(root)
 home=root/'game';state=root/'state';home.mkdir();state.mkdir();protect(home);protect(state)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 cfg={'home':str(home),'state':str(state),'session_verification_seconds':12,
  'native_platform':{'version':1,'python':sys.executable,'services':{'body':'body','controller':'controller'},'driver':str(DRIVER),'config':str(root/'driver.json')},
  'service_connection':{'id':'minecraft-native-fixture','label':'Native fixture','revision':'a'*64,'context_provider_ids':['minecraft:native-fixture']}}
 task={'id':'original','status':'budget_exhausted','turns':8}
 initial(home/'workshop.json',{'task':task,'turn':None,'inbox':[],'unknown_receipts':['preserved']})
 gamecfg={'control_port':port,'token':'disposable-fixture-only'};initial(home/'config.json',gamecfg)
 (home/'app').mkdir();protect(home/'app')
 for item in (BUNDLE/'app').glob('*.py'):shutil.copyfile(item,home/'app'/item.name);protect(home/'app'/item.name)
 peer=root/'peer.py';shutil.copyfile(SOURCE/'tests/session_probe_fixture.py',peer);log=root/'acp.jsonl'
 endpoint={'command':[sys.executable,str(peer)],'cwd':str(root),'env':{'PROBE_LOG':str(log)}}
 effective={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':f'http://127.0.0.1:{port}/mcp',
   'headers':[{'name':'Authorization','value':'Bearer disposable-fixture-only'}]}]}
 initial(home/'endpoint.json',endpoint)
 initial(home/'session.json',{'session':'original-fixture-session','binding':hashlib.sha256(json.dumps(effective,sort_keys=True).encode()).hexdigest()})
 (home/'venv').mkdir();protect(home/'venv');(home/'venv/original.txt').write_text('retained environment')
 candidate=state/'candidate';candidate.mkdir();protect(candidate)
 shutil.copytree(home/'app',candidate/'app');protect(candidate/'app')
 (candidate/'app/candidate-marker.txt').write_text('reviewed candidate source')
 (candidate/'venv').mkdir();protect(candidate/'venv');(candidate/'venv/candidate.txt').write_text('reviewed candidate environment')
 targets={k:{'root':'state','path':'candidate/'+k} for k in ('app','venv')}
 original={p.name:p.read_bytes() for p in home.iterdir() if p.is_file()}
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
  else:manager='scheduled_task'
  if definition:definition.parent.mkdir(parents=True,exist_ok=True)
  units.append((name,definition))
  argv=[str(script),'--role',role,'--home',str(home),'--driver',str(DRIVER),'--driver-config',str(drivercfg),'--shared',str(SHARED/'support/python')]
  service_map[role]={'manager':manager,'name':name,'definition_path':str(definition) if definition else None}
  registrations[role]={'executable':str(DRIVER),'args':['--config',str(drivercfg),'service-run','--service',role],
     'cwd':str(root),'description':'Disposable Minecraft lifecycle '+role,'autostart':False}
  applications[role]={'executable':sys.executable,'args':argv,'cwd':str(root),'identity_path':str(state/(role+'-identity.json'))}
 data={'version':1,'roots':{'home':str(home),'state':str(state)},'locks':{'installation':str(state/'installation.lock')},'services':service_map,'registrations':registrations,'service_applications':applications,'commands':{'session_endpoint':{'executable':endpoint['command'][0],'args':endpoint['command'][1:],'cwd':endpoint['cwd'],'timeout_seconds':200},'session_probe':{'executable':sys.executable,'args':[str(wrapper),'--home',str(home),'--result','{result}','--native-owner-config',str(ownercfg)],'cwd':str(root),'timeout_seconds':200,'result_root':'state'}}}
 data['exchanges']={key:{'lock':'installation','profile':{'current':str(home/key),'roots':{'state':str(state)}}} for key in ('app','venv')}
 drivercfg.write_text(json.dumps(data));protect(drivercfg);validate_driver_mapping(cfg,drivercfg)
 preflight=subprocess.run([str(DRIVER),'--config',str(drivercfg),'serve'],
     input=json.dumps({'version':1,'id':'read-only-preflight','op':'describe'})+'\n',capture_output=True,text=True,timeout=20)
 report['driver_preflight']={'returncode':preflight.returncode,'stdout':preflight.stdout,'stderr':preflight.stderr}
 if preflight.returncode:raise RuntimeError('Native driver configuration failed: '+preflight.stderr)
 with Session(DRIVER,drivercfg) as session:
  io=NativeIO(cfg,session);backend=NativeInstallation(cfg,session)
  with owner_io(io),installation_lock(state/'installation.lock'):
   for kind in ('body','controller'):
    dispatched.append(units[0 if kind=='body' else 1])
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
     exchange=NativeExchange(cfg,session,backend,env['plan']['transaction_id'],env['id'],targets)
     assert exchange.apply()['applied']
     assert (home/'app/candidate-marker.txt').read_text()=='reviewed candidate source'
     assert exchange.apply()['applied']  # observes exact settled identities
     assert exchange.rollback()['rolled_back']
     assert (home/'venv/original.txt').read_text()=='retained environment'
     assert not (home/'app/candidate-marker.txt').exists()
     assert exchange.rollback()['rolled_back']
     report['native_source_exchange']=read(exchange.path)
    assert p.verify('applied')['verified'];assert p.restore('applied')['restored']
    terminal=read(p.path);assert Participant(cfg,env,backend).restore('applied')['restored']
    assert {q.name:q.read_bytes() for q in home.iterdir() if q.is_file()}==original
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
   assert {q.name:q.read_bytes() for q in home.iterdir() if q.is_file()}==original
  report['acp_events']=[json.loads(line) for line in log.read_text().splitlines()]
  assert report['acp_events']==[{'action':'initialize'},{'action':'load','session':'original-fixture-session'}]*3
 report['passed']=True
finally:
 cleanup=NativeServiceApplicationTests()
 cleanup_errors=[]
 for name,definition in dispatched:
  try:cleanup.cleanup(name,definition)
  except Exception as error:cleanup_errors.append({'service':name,'error':repr(error)})
 report['cleanup_errors']=cleanup_errors
 if temp:temp.cleanup()
 report['disposable_units_removed']=not cleanup_errors
 args.receipt.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':report.get('passed',False),'target':manifest['target'],'cycles':len(report['cycles']),'original_session_loads':len(report.get('acp_events',[]))//2}))
