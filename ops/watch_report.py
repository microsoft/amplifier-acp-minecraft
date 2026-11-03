"""Read-only report of real watch use; model selections are not quality scores."""
import argparse,json,statistics,subprocess
from datetime import datetime
from pathlib import Path


def report(root,since,until=None,players=()):
    since_ms=datetime.fromisoformat(since).timestamp()*1000
    until_ms=datetime.fromisoformat(until).timestamp()*1000 if until else float('inf')
    result={'since':since,'until':until,'players':{},'limitations':[
        'A wake recommendation is not proof of the reported event.',
        'A notification delivered during an already-scheduled turn does not demonstrate a saved planner call.',
        'Public requests can independently wake a peer; only watch_applied/wake records an actual watch wake.',
        'Agent-reported completion and creative quality require separate inspection.']}
    for name in players:
        command=['journalctl','--user','-u','minecraft-agent@'+name,'--since',since,'-o','cat','--no-pager']
        if until:command.extend(['--until',until])
        raw=subprocess.check_output(command,text=True)
        events=[]
        for line in raw.splitlines():
            try:
                v=json.loads(line)
                if v.get('kind','').startswith('watch_'):events.append(v)
            except ValueError:pass
        rows=[e for e in events if e['kind']=='watch_evaluated' and e.get('evaluator')!='predicate']
        exact=[e for e in events if e['kind']=='watch_evaluated' and e.get('evaluator')=='predicate']
        path=root/name/'watches.json';state=json.loads(path.read_text()) if path.exists() else {'watches':[]}
        result['players'][name]={
            'watches':[{k:w.get(k) for k in ['id','task_id','spec','status','notification']} for w in state['watches'] if since_ms<=w['created_ms']<until_ms],
            'exact_predicate_matches':len(exact),'decision_calls':len(rows),'median_ms':statistics.median(e['elapsed_ms'] for e in rows) if rows else None,
            'input_tokens':sum((e['result'].get('usage') or {}).get('input_tokens',0) for e in rows),
            'judgments':[{k:r.get(k) for k in ['id','label','wake','shadow','discarded']} for e in rows for r in e.get('receipts',[])],
            'wake_deliveries':sum(e['kind']=='watch_applied' and e.get('application')=='wake' for e in events),
            'advisory_deliveries':sum(e['kind']=='watch_applied' and e.get('application')=='advisory' for e in events),
            'errors':[e for e in events if e['kind'] in ['watch_error','watch_bridge_error']],
        }
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--briefs',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--players',nargs='+',required=True);a=p.parse_args()
    brief=json.loads(a.briefs.read_text())
    result=report(a.root,brief['started_at'],brief.get('ended_at'),a.players)
    a.out.write_text(json.dumps(result,indent=2));a.out.chmod(0o600)
    print(json.dumps({n:{k:v for k,v in r.items() if k not in ['watches','judgments','errors']}|{'errors':len(r['errors'])}
                      for n,r in result['players'].items()}))
