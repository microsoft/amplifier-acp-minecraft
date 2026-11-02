"""Isolated survival supply-chain fixture; never grants production agents items."""
import argparse,json,os,secrets,subprocess,sys,tempfile,time,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command
p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--properties',required=True);a=p.parse_args()
def rcon(text):return command(a.properties,text)
checks=[]
with tempfile.TemporaryDirectory(prefix='survival-course-') as tmp:
 cfg={'username':'SurvivalTester','control_port':18535,'token':secrets.token_hex(32)}
 file=Path(tmp)/'config.json';file.write_text(json.dumps(cfg));os.chmod(file,0o600)
 log=open('evidence/survival-body.log','w');proc=subprocess.Popen([a.node,'body.cjs',str(file)],stdout=log,stderr=log)
 def act(tool,**arguments):return control(cfg,'/action',{'name':tool,'arguments':arguments})
 def turn():control(cfg,'/finish',{});control(cfg,'/turn',{})
 def denied(fragment,name,**kw):
  try:act(name,**kw);raise AssertionError('Expected refusal: '+name)
  except urllib.error.HTTPError as e:assert fragment in e.read().decode()
 try:
  for _ in range(100):
   try:
    if control(cfg,'/status')['ready']:break
   except Exception:pass
   time.sleep(.2)
  else:raise RuntimeError('Body did not connect')
  rcon('forceload add 2992 2992 3024 3024');time.sleep(.5)
  rcon('fill 2998 79 2998 3012 85 3008 air');rcon('fill 2998 80 2998 3012 80 3008 stone')
  rcon('kill @e[type=sheep,tag=survival_fixture]');time.sleep(.2)
  rcon('kill @e[type=item,x=3000,y=81,z=3000,distance=..20]')
  rcon('tp SurvivalTester 3000.5 81 3000.5');rcon('clear SurvivalTester');time.sleep(.6);turn()
  for name,x,nbt in [('adult',3002,'Color:0b,Sheared:0b'),('baby',3002,'Age:-24000,Color:14b'),('shorn',3002,'Color:4b,Sheared:1b')]:
   z={'adult':3000,'baby':3001,'shorn':3002}[name]
   rcon(f'summon sheep {x}.5 81 {z}.5 {{NoAI:1b,Tags:["survival_fixture","{name}"],{nbt}}}')
  time.sleep(.5)
  sheep=act('entities',name='sheep',radius=8)['entities']
  assert len(sheep)==3,sheep
  adult=next(e for e in sheep if e['sheep']['color']=='white');baby=next(e for e in sheep if e['sheep']['color']=='red');shorn=next(e for e in sheep if e['sheep']['color']=='yellow')
  assert adult['sheep']=={'color':'white','sheared':False,'baby':False},adult
  assert baby['sheep']['baby'] and shorn['sheep']['sheared']
  target={'id':adult['id'],'uuid':adult['uuid']}
  denied('identity changed','shear',id=adult['id'],uuid=baby['uuid'])
  denied('adult sheep','shear',id=baby['id'],uuid=baby['uuid'])
  denied('adult sheep','shear',id=shorn['id'],uuid=shorn['uuid'])
  denied('Shears are required','shear',**target)
  checks.append('Entity metadata: adult/baby, color and sheared state; identity and missing-tool guards')
  rcon('setblock 3000 81 3002 furnace');rcon('give SurvivalTester raw_iron 2');rcon('give SurvivalTester coal 1');time.sleep(.3)
  f={'x':3000,'y':81,'z':3002}
  result=act('furnace',**f,operation='load',item='raw_iron',count=2,fuel='coal',fuel_count=1)
  assert result['input']['name']=='raw_iron',result
  assert not any(i['name']=='raw_iron' for i in result['inventory']),result
  denied('input/output must be empty','furnace',**f,operation='load',item='raw_iron',count=2)
  # Server continues processing after the tool has closed its window.
  time.sleep(21)
  result=act('furnace',**f,operation='collect');assert result['collected']=={'name':'iron_ingot','count':2},result
  assert any(i['name']=='iron_ingot' and i['count']==2 for i in result['inventory'])
  assert act('furnace',**f,operation='collect')['collected'] is None
  checks.append('Furnace: load genuine inputs/fuel, refuse duplicate load, close, smelt, verify two collected ingots')
  act('craft',item='shears',count=1)
  # A wall between player and animal must prevent interaction.
  rcon('setblock 3001 82 3000 stone');time.sleep(.2)
  denied('behind a block','shear',**target);rcon('setblock 3001 82 3000 air');time.sleep(.2)
  denied('identity changed','follow',entity_id=adult['id'],uuid=baby['uuid'],seconds=1)
  rcon('tp SurvivalTester 3008.5 81 3000.5');time.sleep(.3)
  result=act('follow',entity_id=adult['id'],uuid=adult['uuid'],seconds=3)
  assert result['within_three_blocks'],result
  checks.append('Animal approach: reject stale identity, follow live target to verified interaction range')
  result=act('shear',**target);assert result['verified'] and result['sheep']['sheep']['sheared']
  assert '1b' in rcon('data get entity @e[type=sheep,tag=adult,limit=1] Sheared')
  denied('adult sheep','shear',**target)
  drops=act('entities',name='item',radius=8)['entities'];assert any(e.get('item',{}).get('name')=='white_wool' for e in drops),drops
  act('move',x=3002,y=81,z=3000,range=0);time.sleep(1)
  assert any(i['name']=='white_wool' for i in act('inventory')['items'])
  checks.append('Survival: craft shears from smelted ingots, refuse blocked line of sight, shear once and collect actual wool')
  turn()
  # Use fixture-only extra wool to ensure the random 1–3 yield cannot make the
  # bed-placement regression flaky. Production agents receive no supplies.
  rcon('give SurvivalTester white_wool 3');rcon('give SurvivalTester oak_planks 3');rcon('setblock 3003 81 3002 crafting_table');time.sleep(.3)
  act('craft',item='white_bed',count=1)
  result=act('place',x=3004,y=81,z=3000,item='white_bed',support_face='up',facing='north')
  foot=act('inspect',x=3004,y=81,z=3000);assert foot['properties']['part']=='foot',foot
  facing=foot['properties']['facing'];assert facing=='north';dx,dz={'north':(0,-1),'south':(0,1),'east':(1,0),'west':(-1,0)}[facing]
  head=act('inspect',x=3004+dx,y=81,z=3000+dz);assert head['name']=='white_bed' and head['properties']['part']=='head',head
  checks.append('Bed: craft and place a real two-block bed, independently inspect foot and head')
  rcon('setblock 3003 81 3002 air');rcon('setblock 3010 81 3002 crafting_table');time.sleep(.2)
  before=control(cfg,'/state')['position']
  denied('no movement performed','craft',item='diamond_pickaxe',count=1)
  assert control(cfg,'/state')['position']==before
  checks.append('Missing recipe: fails before walking to a workbench; player position is unchanged')
  print(json.dumps({'checks':checks},indent=2),flush=True)
 finally:
  rcon('kill @e[type=sheep,tag=survival_fixture]');rcon('forceload remove 2992 2992 3024 3024');proc.terminate();proc.wait(timeout=10);log.close()
