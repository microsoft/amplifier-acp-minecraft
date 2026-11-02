"""Server-verified signs and walk-only navigation, on an isolated test platform.
RCON prepares fixtures only. Tested actions use ordinary survival game tools.
"""
import argparse,concurrent.futures,json,os,secrets,subprocess,sys,tempfile,time,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command

p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--properties',required=True);a=p.parse_args()
os.umask(0o077);Path('evidence').mkdir(exist_ok=True)
checks=[];observations={}
def rcon(text):return command(a.properties,text)
with tempfile.TemporaryDirectory(prefix='visitor-course-') as tmp:
 cfg={'username':'VisitorTester','control_port':18537,'token':secrets.token_hex(32)}
 file=Path(tmp)/'config.json';file.write_text(json.dumps(cfg));log=open('evidence/visitor-body.log','w')
 def start():
  proc=subprocess.Popen([a.node,'body.cjs',str(file)],stdout=log,stderr=log)
  for _ in range(100):
   try:
    if control(cfg,'/status')['ready']:return proc
   except Exception:pass
   time.sleep(.2)
  proc.terminate();raise RuntimeError('Test body did not connect')
 def act(name,**arguments):return control(cfg,'/action',{'name':name,'arguments':arguments})
 def turn():control(cfg,'/finish',{});control(cfg,'/turn',{})
 def teleport(x,y,z):rcon(f'tp VisitorTester {x}.5 {y} {z}.5');time.sleep(.5)
 def rejects(name,match,**arguments):
  try:act(name,**arguments);raise AssertionError('Unexpected success: '+name)
  except urllib.error.HTTPError as e:
   error=e.read().decode();assert match in error,error
 def passed(text):checks.append(text);print(text,flush=True)
 proc=start()
 try:
  rcon('forceload add 2992 2992 3040 3024');time.sleep(1)
  rcon('fill 2998 80 2998 3030 80 3010 stone');rcon('fill 2998 81 2998 3030 87 3010 air')
  for cmd in ['fill 2999 81 2999 3008 81 2999 stone','fill 2999 81 3005 3008 81 3005 stone','fill 2999 81 2999 2999 81 3005 stone','fill 3008 81 2999 3008 81 3005 stone','fill 3002 81 2999 3002 81 3002 oak_planks','setblock 3004 81 3000 oak_pressure_plate']:
   rcon(cmd)
  teleport(3000,81,3000);turn()
  route=act('plan_route',x=3004,y=81,z=3000,mode='walk_only');assert route['reachable']
  assert max(v['z'] for v in route['steps'])>=3003 and all(v['y']==81 for v in route['steps'])
  trip=act('move',x=3004,y=81,z=3000,mode='walk_only');observations['trip']=trip
  assert trip['reached'] and trip['observation']['max_feet_y']<=81.125 and trip['observation']['min_feet_y']>=80.95
  assert act('inspect',x=3004,y=81,z=3000)['properties']['powered']
  act('move',x=3000,y=81,z=3000,mode='walk_only');time.sleep(.2)
  assert not act('inspect',x=3004,y=81,z=3000)['properties']['powered']
  passed('Level detour around a one-block wall; goal pressure plate activates and resets')
  rcon('fill 3002 81 3003 3002 81 3004 oak_planks');time.sleep(.2)
  assert not act('plan_route',x=3004,y=81,z=3000,mode='walk_only')['reachable']
  rejects('move','No walk-only route',x=3004,y=81,z=3000,mode='walk_only')
  assert act('plan_route',x=3004,y=81,z=3000,mode='normal')['reachable']
  passed('Closed level route is refused even when normal navigation can jump the wall')
  teleport(3010,81,3000);turn()
  with concurrent.futures.ThreadPoolExecutor() as pool:
   future=pool.submit(act,'move',x=3028,y=81,z=3000,mode='walk_only');time.sleep(.7);control(cfg,'/stop',{})
   try:future.result(timeout=5);raise AssertionError('Stop did not interrupt walking')
   except urllib.error.HTTPError:pass
  pos=control(cfg,'/state')['position'];time.sleep(.5);after=control(cfg,'/state')['position']
  assert abs(pos['x']-after['x'])<.3 and not control(cfg,'/status')['turn_active']
  passed('Stop interrupts the walk and releases movement')
  teleport(3014,81,2999);turn();rcon('clear VisitorTester');rcon('give VisitorTester oak_sign 3');time.sleep(.3)
  placed=act('place',x=3014,y=81,z=3001,item='oak_sign',support_face='up',facing='north')
  assert placed['actual']=='oak_sign' and int(placed['properties']['rotation'])==8
  desired=['POCKET TEST','Enter by WHITE','Touch goal pad','Return to exit']
  written=act('write_sign',x=3014,y=81,z=3001,lines=desired,expected_lines=[''])
  assert written['verified'] and written['front']==desired
  assert 'POCKET TEST' in rcon('data get block 3014 81 3001 front_text')
  rejects('write_sign','facing the front',x=3014,y=81,z=3001,side='back',lines=['Back test'])
  act('move',x=3014,y=81,z=3003,mode='walk_only')
  back=act('write_sign',x=3014,y=81,z=3001,side='back',lines=['WALK ONLY','No wall jumps'])
  assert back['front']==desired and back['back'][0]=='WALK ONLY';observations['sign']=back
  rejects('write_sign','text changed',x=3014,y=81,z=3001,side='back',lines=['Wrong'],expected_lines=['stale'])
  passed('Standing sign faces the requested direction; front and back persist separately, stale/wrong-side edits refused')
  turn();teleport(3018,81,3000);rcon('setblock 3018 82 3002 oak_planks');time.sleep(.2)
  placed=act('place',x=3018,y=82,z=3001,item='oak_sign',support_face='north',facing='north')
  assert placed['actual']=='oak_wall_sign'
  written=act('write_sign',x=3018,y=82,z=3001,lines=['WALL SIGN','Verified text'])
  assert written['verified'];rcon('data merge block 3018 82 3001 {is_waxed:1b}');time.sleep(.3)
  rejects('write_sign','waxed',x=3018,y=82,z=3001,lines=['Should fail'])
  passed('Wall-sign item/block conversion works; waxed sign stays unchanged')
  control(cfg,'/finish',{});proc.terminate();proc.wait(timeout=10);proc=start()
  reread=act('read_sign',x=3014,y=81,z=3001)
  assert reread['front']==desired and reread['back'][0]=='WALK ONLY'
  passed('Sign text remains readable after reconnect without an active turn')
  Path('evidence/visitor-live.json').write_text(json.dumps({'checks':checks,'observations':observations},indent=2))
 finally:
  rcon('forceload remove 2992 2992 3040 3024');proc.terminate();proc.wait(timeout=10);log.close()
