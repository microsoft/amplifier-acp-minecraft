"""Read-only experiment measurements; counts are not scores of agent quality."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import statistics


def analyze(root, started_at, players):
    since=datetime.fromisoformat(started_at).timestamp()
    report={'since':started_at,'players':{},'limitations':[
        'Task progress is agent-reported; inspect artifacts independently.',
        'Repeated failures are exact action/argument matches, not a semantic loop detector.',
        'Assessment recommendations do not establish that they caused a later action.',
        'A before/after run with different goals is observational, not a controlled comparison.']}
    for name in players:
        home=root/name; data=json.loads((home/'workshop.json').read_text())
        events=[e for e in data.get('events',[]) if e.get('time','') >= started_at]
        failures=[]; repeats=0; seen=set()
        for e in events:
            if e['kind'] not in ('action_failed','action_result'):continue
            key=json.dumps([e.get('action'),e.get('arguments')],sort_keys=True)
            if e['kind']=='action_failed' or (e.get('result') or {}).get('error'):
                repeats+=key in seen;seen.add(key)
                failures.append({'id':e['id'],'at':e['time'],'action':e.get('action'),'error':e.get('error') or e.get('result',{}).get('error')})
            else:seen.discard(key)
        assessment=[]
        for file in ('assessments.previous.jsonl','assessments.jsonl'):
            p=home/file
            if p.exists():
                for line in p.read_text().splitlines():
                    try:
                        r=json.loads(line)
                        if r['time']>=since:assessment.append(r)
                    except (ValueError,KeyError):pass
        choices=Counter(f"{a['name']}:{a.get('choice',a['type'])}" for r in assessment for a in r['result']['answers'])
        task=data.get('task') or {}
        report['players'][name]={
            'task_status':task.get('status'),'goal':task.get('goal'),
            'latest_progress':task.get('progress',[])[-1:],
            'tool_results':sum(e['kind']=='action_result' for e in events),
            'failures':failures,'repeated_failed_attempts':repeats,
            'public_messages':sum(e['kind']=='chat_sent' or (e['kind']=='action_result' and e.get('action') in ('tell','chat')) for e in events),
            'assessments':len(assessment),'choices':dict(choices),
            'median_assessment_ms':statistics.median(r['elapsed_ms'] for r in assessment) if assessment else None,
            'decision_input_tokens':sum((r['result'].get('usage') or {}).get('input_tokens',0) for r in assessment),
        }
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--briefs',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--players',nargs='+',required=True)
    a=p.parse_args();r=analyze(a.root,json.loads(a.briefs.read_text())['started_at'],a.players)
    a.out.write_text(json.dumps(r,indent=2));a.out.chmod(0o600)
    print(json.dumps({n:{k:v for k,v in s.items() if k not in ('latest_progress','failures','goal')} for n,s in r['players'].items()}))
