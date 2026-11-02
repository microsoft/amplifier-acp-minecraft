"""Isolated, server-verified obstacle course. Never modifies the players' inn.
RCON sets up fixtures only; the tested body acts with ordinary survival tools.
"""
import argparse,asyncio,json,os,secrets,subprocess,sys,tempfile,time,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command
from acp_client import Client
p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--properties',required=True);p.add_argument('--model-endpoint',type=Path);a=p.parse_args()
checks=[]
def rcon(text):return command(a.properties,text)
with tempfile.TemporaryDirectory(prefix='spatial-course-') as tmp:
 cfg={'username':'SpatialTester','control_port':18538,'token':secrets.token_hex(32),'bot_names':['BuilderOne','BuilderTwo']}
 file=Path(tmp)/'config.json';file.write_text(json.dumps(cfg));os.chmod(file,0o600)
 log=open('evidence/spatial-body.log','w');proc=subprocess.Popen([a.node,'body.cjs',str(file)],stdout=log,stderr=log)
 def act(name,**arguments):return control(cfg,'/action',{'name':name,'arguments':arguments})
 def turn():control(cfg,'/finish',{});control(cfg,'/turn',{})
 def teleport(x,y,z):rcon(f'tp SpatialTester {x}.5 {y} {z}.5');time.sleep(.6)
 def prepare_pit():
  for cmd in ['fill 1998 80 1998 2005 80 2002 stone','fill 1998 81 1998 2002 83 2002 stone','fill 1999 81 1999 2001 84 2001 air','fill 2003 83 1999 2005 83 2001 stone','clear SpatialTester','give SpatialTester oak_planks 32','give SpatialTester wooden_pickaxe'] :rcon(cmd)
  teleport(2000,81,2000);turn()
 try:
  for _ in range(100):
   try:
    if control(cfg,'/status')['ready']:break
   except Exception:pass
   time.sleep(.2)
  else:raise RuntimeError('Test body did not connect')
  rcon('forceload add 1984 1984 2080 2016');time.sleep(1)
  rcon('fill 1996 79 1996 2075 89 2004 air')
  prepare_pit()
  atlas=act('map',radius=4);assert len(atlas['layers'])==7 and '#' in ''.join(atlas['layers'][3]['rows'])
  assert not act('plan_route',x=2003,y=84,z=2000,range=0)['reachable']
  try:act('dig',x=2000,y=80,z=2000,expected='stone');raise AssertionError('Removed own footing')
  except urllib.error.HTTPError as e:assert 'supporting' in e.read().decode()
  act('dig',x=2002,y=83,z=2000,expected='stone')
  act('place',x=2001,y=81,z=2000,item='oak_planks')
  assert act('plan_route',x=2003,y=84,z=2000,range=0)['reachable']
  result=act('move',x=2003,y=84,z=2000,range=0);assert result['reached'] and int(result['position']['y'])==84
  checks.append('Pit: detect no route, protect footing, dig/place stairs, actually reach surface')
  turn()
  # Three ascending full-block steps with a verified feet-height destination.
  rcon('fill 2010 80 1999 2018 80 2001 stone')
  for x,height in [(2012,81),(2013,82),(2014,83)]:rcon(f'fill {x} 81 1999 {x} {height} 2001 stone')
  teleport(2011,81,2000)
  result=act('move',x=2014,y=84,z=2000,range=0);assert int(result['position']['y'])==84
  checks.append('Stairs: climb three levels and verify actual destination elevation')
  result=act('move',x=2011,y=81,z=2000,range=0);assert int(result['position']['y'])==81
  checks.append('Stairs: descend three consecutive one-block steps; upstream drop limit measures to floor')
  turn()
  rcon('fill 2028 79 1998 2037 80 2002 stone');rcon('fill 2032 80 1998 2034 80 2002 water')
  teleport(2030,81,2000)
  act('place',x=2031,y=81,z=2000,item='oak_planks')
  for x in range(2032,2036):act('place',x=x,y=81,z=2000,item='oak_planks')
  result=act('move',x=2035,y=82,z=2000,range=0);assert int(result['position']['y'])==82
  assert 'passed' in rcon('execute if block 2033 81 2000 oak_planks').lower()
  checks.append('Stream: build a supported bridge and cross above the water')
  turn()
  rcon('fill 2048 80 1998 2058 80 2002 stone');rcon('fill 2053 81 1998 2053 83 2002 oak_planks');rcon('give SpatialTester oak_door');rcon('fill 2048 83 1998 2058 83 2002 stone');rcon('fill 2048 81 1998 2058 82 1998 stone');rcon('fill 2048 81 2002 2058 82 2002 stone')
  teleport(2051,81,2000)
  assert not act('plan_route',x=2053,y=81,z=2000,range=0)['reachable']
  act('dig',x=2053,y=81,z=2000,expected='oak_planks');act('dig',x=2053,y=82,z=2000,expected='oak_planks')
  act('place',x=2053,y=81,z=2000,item='oak_door');act('set_open',x=2053,y=81,z=2000,open=True)
  result=act('move',x=2054,y=81,z=2000,range=0);assert result['reached']
  assert act('inspect',x=2053,y=81,z=2000)['properties']['open']
  checks.append('Doorway: remove two exact blocks, install/open a door, walk through')
  turn();teleport(2050,81,2000);rcon('clear SpatialTester');rcon('setblock 2051 81 2000 coal_ore');time.sleep(.2)
  try:act('dig',x=2051,y=81,z=2000,expected='coal_ore');raise AssertionError('Mined ore without harvest tool')
  except urllib.error.HTTPError as e:assert 'harvesting tool' in e.read().decode()
  assert 'passed' in rcon('execute if block 2051 81 2000 coal_ore').lower()
  checks.append('Harvesting: missing pickaxe is reported before destroying coal ore')
  turn()
  rcon('fill 2060 80 1998 2066 80 2002 stone');rcon('fill 2063 81 1999 2063 83 2001 stone')
  rcon('give SpatialTester ladder 3');teleport(2061,81,2000)
  for y in range(81,84):
   placed=act('place',x=2062,y=y,z=2000,item='ladder',support_face='west')
   assert placed['properties']['facing']=='west'
  result=act('move',x=2063,y=84,z=2000,range=0);assert result['reached']
  checks.append('Ladder: choose and verify a consistent support face, then actually climb to the top')
  turn();teleport(2050,81,2000);rcon('setblock 2051 81 2000 crafting_table');rcon('give SpatialTester oak_planks')
  result=act('place',x=2051,y=82,z=2000,item='oak_planks',support_face='up');assert result['verified']
  assert 'passed' in rcon('execute if block 2051 82 2000 oak_planks').lower()
  checks.append('Interactive support: place a block on a crafting table instead of opening its interface')
  if a.model_endpoint:
   prepare_pit()
   async def model_trial():
    endpoint=json.loads(a.model_endpoint.read_text());endpoint['mcp_servers']=[{'type':'http','name':'minecraft','url':'http://127.0.0.1:18538/mcp','headers':[{'name':'Authorization','value':'Bearer '+cfg['token']}]}]
    client=Client(endpoint,lambda kind,**data:None)
    try:
     await client.start();await client.open_session();client.permission_active=lambda:control(cfg,'/status')['turn_active']
     result=await client.prompt('You control the SpatialTester survival avatar for a spatial reasoning test. Escape the pit and stand with feet at (2003,84,2000). Use only minecraft tools. Use map/observe and route planning to understand the terrain, then choose your own legal actions with the supplied inventory. You may modify this test fixture. Do not use chat, admin commands, filesystem, or other tools. Do not claim success unless your actual position confirms it. The turn is bounded to 220 seconds; report obstacles honestly.',220)
     pos=control(cfg,'/state')['position'];passed=int(pos['x'])==2003 and int(pos['y'])==84 and int(pos['z'])==2000
     Path('evidence/spatial-model.json').write_text(json.dumps({'passed':passed,'position':pos,'response':result},indent=2))
     checks.append('Model-directed pit escape: '+('passed' if passed else 'not solved; see evidence/spatial-model.json'))
    finally:await client.close()
   asyncio.run(model_trial())
  print(json.dumps({'checks':checks},indent=2),flush=True)
 finally:
  rcon('forceload remove 1984 1984 2080 2016');proc.terminate();proc.wait(timeout=10);log.close()
