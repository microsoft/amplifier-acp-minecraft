"""Bulk/mixed-material crafting regression; RCON supplies isolated fixture only."""
import argparse,json,os,secrets,subprocess,sys,tempfile,time,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command
p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--properties',type=Path,required=True)
p.add_argument('--port',type=int,help='Optional translation proxy port; defaults to the disposable server port')
p.add_argument('--log',type=Path,required=True);a=p.parse_args()
properties=dict(line.split('=',1) for line in a.properties.read_text().splitlines() if '=' in line and not line.startswith('#'))
assert int(properties['server-port']) != 25565 and properties['level-name'] == 'container-fixture', 'Use a disposable container-fixture server, never the workshop'
port=a.port or int(properties['server-port'])
assert port != 25565, 'Never connect fixture players to the workshop'
a.log.parent.mkdir(parents=True,exist_ok=True)
def r(cmd):return command(a.properties,cmd)
with tempfile.TemporaryDirectory() as d:
 c={'username':'CraftTester','host':'127.0.0.1','port':port,'control_port':18539,'token':secrets.token_hex(32)};f=Path(d)/'config.json';f.write_text(json.dumps(c))
 log=open(a.log,'w');proc=subprocess.Popen([a.node,'body.cjs',str(f)],stdout=log,stderr=log)
 def act(name,**args):return control(c,'/action',{'name':name,'arguments':args})
 def inv():
  v=act('inventory');assert v['cursor'] is None;assert not any(v['crafting_grid']);return {i['name']:i['count'] for i in v['items']}
 checks=[]
 try:
  for _ in range(80):
   try:
    if control(c,'/state').get('ready'):break
   except Exception:pass
   time.sleep(.2)
  r('forceload add 5000 5000');time.sleep(.5)
  for cmd in ['fill 5000 80 5000 5005 80 5005 stone','fill 5000 81 5000 5005 85 5005 air','setblock 5002 81 5001 crafting_table','tp CraftTester 5001.5 81 5001.5','clear CraftTester','give CraftTester oak_log 18','give CraftTester birch_log 10']:r(cmd)
  time.sleep(.6);control(c,'/turn',{})
  result=act('craft',item='oak_planks',count=8);v=inv();assert v['oak_log']==10 and v['birch_log']==10 and v['oak_planks']==32,(result,v)
  checks.append('8 repeated 2x2 recipes: exact input/output, unrelated birch retained, empty cursor/grid')
  act('craft',item='birch_planks',count=5);v=inv();assert v['birch_log']==5 and v['birch_planks']==20 and v['oak_log']==10,v
  checks.append('Switch material types without swapping or losing source stacks')
  act('craft',item='stick',count=2);v=inv();assert v['stick']==8,v
  act('craft',item='oak_slab',count=2);v=inv();assert v['oak_slab']==12,v
  checks.append('Repeated shaped recipes in personal grid and crafting table')
  act('craft',item='chest',count=2);v=inv();assert v['chest']==2,v
  checks.append('Two complete 3x3 chest recipes, server-confirmed cursor/grid cleanup')
  r('clear CraftTester');r('give CraftTester oak_log 2');time.sleep(.2)
  try:act('craft',item='oak_planks',count=3);raise AssertionError('Expected bounded partial result')
  except urllib.error.HTTPError as e:assert '2 recipe executions completed' in e.read().decode()
  v=inv();assert v=={'oak_planks':8},v
  checks.append('Insufficient bulk request reports exact partial completion; no phantom output')
  print(json.dumps({'checks':checks,'independent_server_inventory':r('data get entity CraftTester Inventory')},indent=2))
 finally:
  r('forceload remove 5000 5000');proc.terminate();proc.wait(timeout=10);log.close()
