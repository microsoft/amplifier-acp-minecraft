"""Read-only experiment recorder. Does not task, steer, restart or mutate players."""
import argparse,collections,datetime,json,os,sys,time,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control

def signals(state,history,now_ms):
    """Explain attention needs from receipts; never infer completion from prose."""
    task=state.get('task') or {};status=task.get('status');result=[]
    if not state.get('ready'):result.append({'code':'disconnected','level':'warning','text':'Player is not connected to the world.'})
    labels={'needs_review':'An interrupted turn needs its effects inspected.',
            'blocked':'The agent reported a blocker.',
            'budget_exhausted':'The authorized time or turn budget has ended.',
            'review':'The agent reported delivery; independent review is still needed.'}
    if status in labels:result.append({'code':status,'level':'warning','text':labels[status]})
    turn=history.get('turn') or {}
    try:age=(now_ms-datetime.datetime.fromisoformat(turn['started_at'].replace('Z','+00:00')).timestamp()*1000)/1000
    except (KeyError,ValueError,TypeError):age=0
    if state.get('turn_active') and age>300:result.append({'code':'long_turn','level':'warning','text':'This turn has been active for over five minutes. Inspect its receipts before retrying.'})
    if status in ('running','waiting') and not state.get('turn_active'):
        latest=max([e.get('time','') for e in history.get('events',[])]+[task.get('started_at','')])
        try:quiet=(now_ms-datetime.datetime.fromisoformat(latest.replace('Z','+00:00')).timestamp()*1000)/1000
        except (ValueError,TypeError):quiet=0
        if quiet>600 and status=='running':result.append({'code':'no_recent_activity','level':'warning','text':'No recorded activity for ten minutes on an active responsibility.'})
        if status=='waiting':result.append({'code':'waiting','level':'info','text':'Waiting for selected evidence; a quiet agent may be behaving correctly.'})
    return result

def sample(root,names,out):
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result={'at':now,'players':{}}
    for name in names:
        home=root/name
        try:
            cfg=json.loads((home/'config.json').read_text());s=control(cfg,'/state')
            history=json.loads((home/'workshop.json').read_text());events=history.get('events',[])
            cursor=out/(name+'-seen.json');seen=set(json.loads(cursor.read_text())) if cursor.exists() else set()
            new=[e for e in events if e['id'] not in seen]
            with (out/(name+'-events.jsonl')).open('a') as f:
                for e in new:f.write(json.dumps(e)+'\n')
            cursor.write_text(json.dumps([e['id'] for e in events]));cursor.chmod(0o600)
            task=s.get('task') or {}
            result['players'][name]={k:s.get(k) for k in ('ready','busy','turn_active','position','inventory','health')}
            result['players'][name]['task']={k:task.get(k) for k in ('id','goal','status','turns','max_turns','deadline','wait_for')}
            result['players'][name]['latest_progress']=task.get('progress',[])[-1:]
            result['players'][name]['new_events']=len(new)
            result['players'][name]['signals']=signals(s,history,time.time()*1000)
            result['players'][name]['recoveries']=task.get('recovery_attempts',0)
            result['players'][name]['remaining_seconds']=max(0,int(((task.get('deadline') or 0)-time.time()*1000)/1000))
            result['players'][name]['remaining_turns']=max(0,(task.get('max_turns') or 0)-(task.get('turns') or 0))
            result['players'][name]['new_action_receipts']=sum(e.get('kind') in ('action_result','action_failed') for e in new)
        except Exception as e:result['players'][name]={'error':type(e).__name__}
    previous_file=out/'attention-state.json';previous=json.loads(previous_file.read_text()) if previous_file.exists() else {}
    current={name:{'task':s.get('task',{}).get('id'),'codes':sorted([x['code'] for x in s.get('signals',[]) if x['level']=='warning']+(['unavailable'] if s.get('error') else []))} for name,s in result['players'].items()}
    changes=[{'at':now,'player':name,'task':value['task'],'codes':value['codes'],'signals':result['players'][name].get('signals',[])} for name,value in current.items() if value!=previous.get(name) and (value['codes'] or previous.get(name,{}).get('codes'))]
    if changes:
        with (out/'attention-changes.jsonl').open('a') as f:
            for change in changes:f.write(json.dumps(change)+'\n')
    previous_file.write_text(json.dumps(current));previous_file.chmod(0o600)
    result['attention_changes']=changes
    with (out/'samples.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
    tmp=out/'latest.tmp';tmp.write_text(json.dumps(result,indent=2));tmp.replace(out/'latest.json')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--players',nargs='+',required=True);p.add_argument('--seconds',type=int,default=10800);p.add_argument('--once',action='store_true');a=p.parse_args()
    os.umask(0o077);a.out.mkdir(parents=True,exist_ok=True);end=time.monotonic()+a.seconds
    while True:
        r=sample(a.root,a.players,a.out)
        print(json.dumps({'at':r['at'],'states':{n:s.get('task',{}).get('status',s.get('error')) for n,s in r['players'].items()}}),flush=True)
        if a.once or time.monotonic()>=end:break
        time.sleep(20)
