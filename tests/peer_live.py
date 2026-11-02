"""Two independent bodies communicate only through Minecraft chat."""
import json,os,secrets,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
node=sys.argv[1]
with tempfile.TemporaryDirectory(prefix='minecraft-peer-') as tmp:
 configs=[];processes=[]
 try:
  for name,port in [('TestSender',18536),('TestReceiver',18537)]:
   home=Path(tmp)/name;home.mkdir()
   cfg={'username':name,'control_port':port,'token':secrets.token_hex(32),'bot_names':['TestSender','TestReceiver'],'agent_dialogue':True}
   file=home/'config.json';file.write_text(json.dumps(cfg));os.chmod(file,0o600);configs.append(cfg)
   log=open(f'evidence/{name}.log','w');processes.append((subprocess.Popen([node,'body.cjs',str(file)],stdout=log,stderr=log),log))
  for cfg in configs:
   for _ in range(100):
    try:
     if control(cfg,'/status')['ready']:break
    except Exception:pass
    time.sleep(.2)
   else:raise RuntimeError('Player not ready')
  sender,receiver=configs
  control(receiver,'/task',{'text':'Observe this bounded peer communication test.'});control(receiver,'/inbox')
  control(sender,'/turn',{})
  for intent in ('update','ack'):
   result=control(sender,'/action',{'name':'tell','arguments':{'player':'TestReceiver','text':'Fixture status, no action needed.','intent':intent}});time.sleep(.2)
   assert not result['requests_reply']
   assert control(receiver,'/inbox')==[]
  control(sender,'/action',{'name':'chat','arguments':{'text':'I can see TestReceiver nearby.'}});time.sleep(.3)
  assert control(receiver,'/inbox')==[]
  result=control(sender,'/action',{'name':'tell','arguments':{'player':'TestReceiver','text':'Verified test handoff; please acknowledge.'}})
  assert result['sent'].startswith('@TestReceiver ')
  for _ in range(30):
   messages=control(receiver,'/inbox')
   if messages:break
   time.sleep(.1)
  assert len(messages)==1 and messages[0]['source']=='agent',messages
  events=control(receiver,'/state')['events'];assert any(e.get('route')=='peer_direct' for e in events)
  control(sender,'/finish',{})
  control(receiver,'/turn',{})
  request=next(e['id'] for e in events if e['kind']=='chat' and e.get('source')=='human' and e.get('accepted'))
  task=control(receiver,'/action',{'name':'work_begin','arguments':{'request_id':request,'goal':'fixture'}})
  control(receiver,'/action',{'name':'work_report','arguments':{'status':'blocked','summary':'fixture blocker'}})
  result=control(receiver,'/action',{'name':'work_note','arguments':{'task_id':task['id'],'summary':'fixture blocker resolved; review remaining work','blocker_resolved':True}})
  assert result['status']=='needs_review'
  control(receiver,'/finish',{})
  status=control(receiver,'/status');assert status['task']['last_observed']['position']
  assert status['task']['status']=='needs_review' and not status['turn_active']
  assert any(e.get('route')=='peer_update' for e in events) and any(e.get('route')=='peer_ack' for e in events)
  print(json.dumps({'checks':['Updates and acknowledgments remain visible without waking a peer','Ordinary mention does not wake peer','Explicit tell routes once through Minecraft chat','Peer routing is observable','Recovery note and checkpoint persist without scheduling work']}))
 finally:
  for proc,log in processes:proc.terminate()
  for proc,log in processes:proc.wait(timeout=10);log.close()
