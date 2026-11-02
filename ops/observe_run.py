"""Read-only experiment recorder. Does not task, steer, restart or mutate players."""
import argparse,collections,datetime,json,os,sys,time,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapter import control

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
        except Exception as e:result['players'][name]={'error':type(e).__name__}
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
