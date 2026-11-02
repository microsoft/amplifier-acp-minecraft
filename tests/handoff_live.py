"""Physical handoffs between separate bodies in an isolated fixture."""
import argparse,json,os,secrets,subprocess,sys,tempfile,time,urllib.error,concurrent.futures
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command
p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--properties',required=True);a=p.parse_args()
def rcon(cmd):return command(a.properties,cmd)
checks=[];results=[]
with tempfile.TemporaryDirectory(prefix='handoff-fixture-') as tmp:
 procs=[];cs=[]
 try:
  for name,port in [('HandoffGiver',18533),('HandoffTaker',18534)]:
   home=Path(tmp)/name;home.mkdir();cfg={'username':name,'control_port':port,'token':secrets.token_hex(32),'bot_names':['HandoffGiver','HandoffTaker']};cs.append(cfg)
   path=home/'config.json';path.write_text(json.dumps(cfg));os.chmod(path,0o600)
   log=open('evidence/'+name+'.log','w');procs.append((subprocess.Popen([a.node,'body.cjs',str(path)],stdout=log,stderr=log),log))
  for c in cs:
   for _ in range(100):
    try:
     if control(c,'/status')['ready']:break
    except Exception:pass
    time.sleep(.2)
   else:raise RuntimeError('Body not ready')
  giver,taker=cs
  def act(c,tool,**arguments):return control(c,'/action',{'name':tool,'arguments':arguments})
  def give():return act(giver,'give',player='HandoffTaker',item='oak_planks',count=4)
  def denied(text,fn):
   try:fn();raise AssertionError('Expected refusal')
   except urllib.error.HTTPError as e:assert text in e.read().decode()
  rcon('forceload add 3984 3984 4032 4016');time.sleep(.5)
  rcon('fill 3998 80 3998 4012 80 4004 stone');rcon('fill 3998 81 3998 4012 85 4004 air')
  def reset(x=4002.5):
   rcon('kill @e[type=item,x=4000,y=81,z=4000,distance=..20]')
   for name in ('HandoffGiver','HandoffTaker'):rcon('clear '+name)
   rcon('tp HandoffGiver 4000.5 81 4000.5');rcon(f'tp HandoffTaker {x} 81 4000.5');rcon('give HandoffGiver oak_planks 8');time.sleep(.5)
   control(giver,'/finish',{});control(giver,'/turn',{})
  reset()
  result=give();results.append(result);assert result['status']=='pickup_observed',result
  inv=act(taker,'inventory')['items'];assert sum(i['count'] for i in inv if i['name']=='oak_planks')==4,inv
  assert result['sender_inventory_change']==-4
  checks.append('Stationary recipient: server pickup receipt matches independently refreshed receiver inventory')
  reset(4008.5);before=control(giver,'/state')['position'];denied('within 2.5',give)
  assert control(giver,'/state')['position']==before
  assert sum(i['count'] for i in act(giver,'inventory')['items'] if i['name']=='oak_planks')==8
  checks.append('Distant recipient: no chasing, no movement, no dropped items')
  reset(4001.5);denied('two blocks apart',give)
  assert sum(i['count'] for i in act(giver,'inventory')['items'] if i['name']=='oak_planks')==8
  checks.append('Too-close recipient: refuses self-pickup geometry before dropping items')
  reset()
  with concurrent.futures.ThreadPoolExecutor() as pool:
   future=pool.submit(lambda:denied('moving',give));time.sleep(.2);rcon('tp HandoffTaker 4002.8 81 4000.5');future.result()
  assert sum(i['count'] for i in act(giver,'inventory')['items'] if i['name']=='oak_planks')==8
  checks.append('Moving recipient: refuses before dropping any inventory')
  reset();rcon('give HandoffTaker cobblestone 2304');time.sleep(.3)
  result=give();results.append(result);assert result['status']!='pickup_observed',result
  assert not any(i['name']=='oak_planks' for i in act(taker,'inventory')['items'])
  assert result['drops'],result
  checks.append('Full inventory: no false delivery claim; reports the physical drop for recovery')
  reset();rcon('setblock 4001 81 4000 stone');rcon('setblock 4001 82 4000 stone');time.sleep(.2)
  denied('behind a block',give)
  checks.append('Obstructed recipient: refuses a handoff through a wall')
  print(json.dumps({'checks':checks,'receipts':results},indent=2),flush=True)
 finally:
  rcon('kill @e[type=item,x=4000,y=81,z=4000,distance=..20]');rcon('forceload remove 3984 3984 4032 4016')
  for proc,log in procs:proc.terminate()
  for proc,log in procs:proc.wait(timeout=10);log.close()
