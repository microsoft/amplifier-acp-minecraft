"""Real controller/body test of hourly deferral. No world edits or model calls."""
import argparse,json,os,secrets,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control

p=argparse.ArgumentParser();p.add_argument('--node',required=True);a=p.parse_args()
os.umask(0o077);Path('evidence').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='capacity-test-') as tmp:
 home=Path(tmp);cfg={'username':'CapacityTester','control_port':18536,'token':secrets.token_hex(32)}
 (home/'config.json').write_text(json.dumps(cfg))
 (home/'endpoint.json').write_text(json.dumps({'command':[sys.executable,str(Path('tests/work_fixture.py').resolve())],'cwd':tmp}))
 log=open('evidence/capacity-live.log','w');body=subprocess.Popen([a.node,'body.cjs',str(home/'config.json')],stdout=log,stderr=log);controller=None
 def start_controller():
  return subprocess.Popen([sys.executable,'adapter.py','--home',tmp],stdout=log,stderr=log)
 try:
  for _ in range(100):
   try:
    if control(cfg,'/status')['ready']:break
   except Exception:pass
   time.sleep(.2)
  else:raise RuntimeError('Body did not connect')
  # A long human brief remains queued until capacity returns, then runs normally.
  (home/'calls.json').write_text(json.dumps([time.time()-3592]*30));controller=start_controller();time.sleep(.4)
  brief='Please carry out this bounded fixture request. '+('Detailed requirement. '*180)
  assert len(brief)>2000
  control(cfg,'/task',{'text':brief});time.sleep(1)
  state=control(cfg,'/state');assert state['pending_messages']==1 and not state['turn_active']
  for _ in range(100):
   state=control(cfg,'/state');task=state.get('task') or {}
   if task.get('status')=='review':break
   time.sleep(.2)
  else:raise AssertionError('Deferred task did not run')
  assert task['request']==brief and task['turns']==2
  print('Deferred long brief survives hourly capacity wait and completes both fixture turns',flush=True)
  controller.terminate();controller.wait(timeout=5);controller=None
  # Stop while waiting clears the queued request. Capacity does not revive it.
  (home/'calls.json').write_text(json.dumps([time.time()-3592]*30));controller=start_controller();time.sleep(.4)
  control(cfg,'/task',{'text':'This queued request will be cancelled before capacity returns.'});time.sleep(.5)
  assert control(cfg,'/state')['pending_messages']==1
  control(cfg,'/stop',{});time.sleep(10)
  state=control(cfg,'/state');assert state['pending_messages']==0 and not state['turn_active'] and state['task']['id']==task['id']
  calls=json.loads((home/'calls.json').read_text());assert len(calls)==30 and all(t<time.time()-3600 for t in calls)
  print('Stop cancels queued work; returning hourly capacity starts no new turn',flush=True)
 finally:
  if controller:controller.terminate();controller.wait(timeout=5)
  body.terminate();body.wait(timeout=10);log.close()
