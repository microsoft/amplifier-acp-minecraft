"""Real body/MCP rework and inbox regression; no model calls or block edits."""
import argparse,json,os,secrets,subprocess,tempfile,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control
p=argparse.ArgumentParser();p.add_argument('--node',required=True);p.add_argument('--port',type=int,default=25565);a=p.parse_args()
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='minecraft-review-') as tmp:
 root=Path(tmp);bodies={};cfgs={};logs=[]
 def start(name):
  cfg=cfgs[name];log=open(root/(name+'.log'),'a');logs.append(log)
  bodies[name]=subprocess.Popen([a.node,'body.cjs',str(root/name/'config.json')],stdout=log,stderr=log)
  for _ in range(100):
   try:
    if control(cfg,'/status')['ready']:return
   except Exception:pass
   time.sleep(.2)
  raise RuntimeError('Fixture body did not connect: '+name)
 def turn(cfg,messages=None):
  s=control(cfg,'/state');return control(cfg,'/turn',{'expected_generation':s['generation'],'peer_only':bool(messages),'message_ids':[m['id'] for m in messages or []]})
 def action(cfg,name,args):return control(cfg,'/action',{'name':name,'arguments':args})
 try:
  for i,name in enumerate(['ReviewLead','ReviewWorker']):
   h=root/name;h.mkdir();cfg={'username':name,'port':a.port,'control_port':18538+i,'token':secrets.token_hex(32),'bot_names':['ReviewLead','ReviewWorker'],'agent_dialogue':True,'task_max_turns':8}
   cfgs[name]=cfg;(h/'config.json').write_text(json.dumps(cfg));start(name)
  w=cfgs['ReviewWorker'];l=cfgs['ReviewLead']
  req=control(w,'/task',{'text':'Inspect a fixture and make in-scope corrections requested by ReviewLead. No world edits.','reviewers':['ReviewLead']})
  queued=control(w,'/inbox/peek');assert len(queued)==1
  # A body restart retains exactly the same queued request without consuming it.
  bodies['ReviewWorker'].terminate();bodies['ReviewWorker'].wait(timeout=10);start('ReviewWorker')
  assert control(w,'/inbox/peek')==queued
  turn(w,queued);task=action(w,'work_begin',{'request_id':req['request_id'],'goal':'Fixture inspection'})
  action(w,'work_report',{'status':'review','summary':'Inspection ready'});control(w,'/finish',{})
  original={k:task[k] for k in ['id','deadline','max_turns','request_id']}
  turn(l);action(l,'tell',{'player':'ReviewWorker','text':'Fixture FYI only.','intent':'update'});control(l,'/finish',{});time.sleep(1)
  assert control(w,'/inbox/peek')==[]
  turn(l);action(l,'tell',{'player':'ReviewWorker','text':'Please re-inspect the fixture before closing our existing task.','intent':'request'});control(l,'/finish',{})
  for _ in range(30):
   incoming=control(w,'/inbox/peek')
   if incoming:break
   time.sleep(.1)
  assert len(incoming)==1;turn(w,incoming)
  task=action(w,'work_reopen',{'task_id':task['id'],'request_id':incoming[0]['id'],'reason':'The existing inspection requires one correction.'})
  assert task['status']=='running' and task['turns']==2
  assert {k:task[k] for k in original}==original
  assert json.loads((root/'ReviewWorker/workshop.json').read_text())['turn']['may_mutate']
  action(w,'work_report',{'status':'review','summary':'Correction inspected; no world edits.'});control(w,'/finish',{})
  control(w,'/stop',{});assert control(w,'/status')['task']['status']=='stopped'
  print('PASS: durable inbox; FYI stays quiet; named public correction reopens same bounded task; Stop revokes review.')
 finally:
  for proc in bodies.values():
   if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
  for log in logs:log.close()
