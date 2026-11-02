"""Explicit integration test: uses a separate player and remote test platform.
Run only against the workshop server; requires its operator RCON properties.
"""
import argparse,concurrent.futures,json,os,secrets,subprocess,sys,tempfile,time,urllib.error,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command

p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--properties',required=True);a=p.parse_args()
checks=[]
with tempfile.TemporaryDirectory(prefix='minecraft-adapter-test-') as tmp:
 cfg={'username':'WorkshopTester','control_port':18539,'token':secrets.token_hex(32),'context_token':secrets.token_hex(32),'context_grant':secrets.token_hex(32),'bot_names':['BuilderOne','BuilderTwo']}
 f=Path(tmp)/'config.json';f.write_text(json.dumps(cfg));os.chmod(f,0o600)
 log=open('evidence/test-body.log','w')
 proc=subprocess.Popen([a.node,'body.cjs',str(f)],stdout=log,stderr=log)
 try:
  for n in range(100):
   try:
    if control(cfg,'/state').get('ready'):break
   except Exception:pass
   time.sleep(.2)
  else:raise RuntimeError('Test player did not connect')
  checks.append('Minecraft login/spawn')
  try:urllib.request.urlopen('http://127.0.0.1:18539/state');raise AssertionError('Missing auth accepted')
  except urllib.error.HTTPError as e:assert e.code==401
  checks.append('Control authentication')
  def act(name,**args):
   r=control(cfg,'/action',{'name':name,'arguments':args});print(name,r,file=sys.stderr);return r
  try:act('chat',text='unexpected');raise AssertionError('Inactive turn accepted')
  except urllib.error.HTTPError as e:assert e.code==400
  checks.append('No actions outside active turn')
  command(a.properties,'forceload add 996 996 1006 1006');time.sleep(2)
  for cmd in ['fill 996 80 996 1006 80 1006 grass_block','fill 996 81 996 1006 88 1006 air','tp WorkshopTester 1000.5 81 1000.5','clear WorkshopTester','setblock 1002 81 1000 oak_log']:
   command(a.properties,cmd)
  time.sleep(1)
  control(cfg,'/turn',{})
  for name,args in [('chat',{'text':'/op WorkshopTester'}),('move',{'x':99999,'y':81,'z':1000}),('gather',{'block':'oak_log','count':999})]:
   try:act(name,**args);raise AssertionError('Invalid action accepted')
   except urllib.error.HTTPError as e:assert e.code==400
  checks.append('Reject commands, far coordinates, oversized actions')
  act('move',x=999,y=81,z=1003,range=1)
  assert control(cfg,'/state')['position']['z']>1001
  checks.append('Actual pathfinding movement')
  act('gather',block='oak_log',count=1)
  assert any(i['name']=='oak_log' for i in control(cfg,'/state')['inventory'])
  checks.append('Actual mining and pickup')
  act('craft',item='oak_planks',count=1)
  assert any(i['name']=='oak_planks' and i['count']==4 for i in control(cfg,'/state')['inventory'])
  checks.append('Actual crafting')
  r=act('build',item='oak_planks',blocks=[{'x':1001,'y':81,'z':1002},{'x':1002,'y':81,'z':1002}])
  assert len(r['placed'])==2,r
  assert act('inspect',x=1001,y=81,z=1002)['name']=='oak_planks'
  assert 'passed' in command(a.properties,'execute if block 1002 81 1002 oak_planks').lower()
  checks.append('Actual multi-block build, verified by server')
  req=urllib.request.Request('http://127.0.0.1:18539/mcp',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'observe','arguments':{}}}).encode(),headers={'Authorization':'Bearer '+cfg['token'],'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
  response=json.load(urllib.request.urlopen(req));assert json.loads(response['result']['content'][0]['text'])['username']=='WorkshopTester'
  checks.append('MCP protocol returns live player state')
  for _ in range(24):
   try:act('move',x=99999,y=81,z=1000)
   except urllib.error.HTTPError:pass
  assert control(cfg,'/reply',{'text':'Workshop integration check complete.'})['sent']
  checks.append('Final reply remains available after action budget')
  control(cfg,'/task',{'text':'queued task'});control(cfg,'/finish',{})
  assert len(control(cfg,'/inbox'))==1
  checks.append('Turn completion preserves new messages')
  control(cfg,'/turn',{})
  with concurrent.futures.ThreadPoolExecutor() as pool:
   future=pool.submit(act,'follow',player='WorkshopTester',seconds=15)
   time.sleep(1);control(cfg,'/stop',{})
   try:future.result(timeout=5);raise AssertionError('Follow was not cancelled')
   except urllib.error.HTTPError:pass
  assert not control(cfg,'/status')['turn_active']
  try:control(cfg,'/reply',{'text':'late reply'});raise AssertionError('Stopped turn accepted a reply')
  except urllib.error.HTTPError as e:assert e.code==400
  checks.append('Stop interrupts active action')
  stale=control(cfg,'/state')['generation'];control(cfg,'/stop',{})
  try:control(cfg,'/turn',{'expected_generation':stale});raise AssertionError('Stale turn survived Stop')
  except urllib.error.HTTPError as e:assert e.code==400
  try:control(cfg,'/turn',{'continuation':True});raise AssertionError('Continuation without running work')
  except urllib.error.HTTPError as e:assert e.code==400
  checks.append('Stop prevents a queued stale continuation from starting')
  control(cfg,'/task',{'text':'Build a test shelter over several turns'})
  control(cfg,'/turn',{})
  request_id=next(e['id'] for e in reversed(control(cfg,'/state')['events']) if e['kind']=='chat' and e.get('accepted'))
  task=act('work_begin',request_id=request_id,goal='test shelter');assert task['status']=='running'
  act('work_report',status='running',summary='Verified starting platform')
  control(cfg,'/finish',{});assert control(cfg,'/status')['task']['status']=='running'
  control(cfg,'/turn',{});assert control(cfg,'/status')['task']['turns']==2
  def query(token,payload):
   req=urllib.request.Request('http://127.0.0.1:18539/context/v1/query',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
   return json.load(urllib.request.urlopen(req))
  try:query(cfg['token'],{'operation':'list','access':{'mode':'owner'}});raise AssertionError('Game token accessed context')
  except urllib.error.HTTPError as e:assert e.code==401
  rows=query(cfg['context_token'],{'operation':'list','access':{'mode':'owner'}})
  assert rows['items'][0]['activity']['task']['goal']=='test shelter'
  grant=query(cfg['context_token'],{'operation':'authorize','access':{'mode':'grant','grant':cfg['context_grant']}})
  assert grant['owner'] is False
  control(cfg,'/stop',{});assert control(cfg,'/status')['task']['status']=='stopped'
  checks.append('Persistent multi-turn task lifecycle and cancellation')
  checks.append('Context provider uses separate credential and non-owner room grant')
  # A separate ACP implementation drives the actual controller through two turns.
  control(cfg,'/inbox')
  endpoint={'command':[sys.executable,str(Path('tests/work_fixture.py').resolve())],'cwd':tmp}
  (Path(tmp)/'endpoint.json').write_text(json.dumps(endpoint))
  controller=subprocess.Popen([sys.executable,'adapter.py','--home',tmp],stdout=log,stderr=log)
  try:
   control(cfg,'/task',{'text':'Please run the two-turn fixture task'})
   for _ in range(100):
    status=control(cfg,'/status');task=status.get('task') or {}
    if task.get('goal')=='fixture two-turn task' and task['status']=='review':break
    time.sleep(.2)
   else:raise AssertionError('Controller did not finish two-turn work')
   assert task['turns']==2 and len(task['progress'])==2,task
   checks.append('Independent ACP peer completes two controller turns without a second human message')
  finally:controller.terminate();controller.wait(timeout=5)
  print(json.dumps({'passed':checks},indent=2))
 finally:
  command(a.properties,'forceload remove 996 996 1006 1006')
  proc.terminate();proc.wait(timeout=10);log.close()
