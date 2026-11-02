"""Explicit live semantic evaluation; no game actions. Includes option-order replay."""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
import tempfile
from attention import Attention
from assessment import POLICY


async def main(args):
    config=json.loads((args.home/'config.json').read_text())['decision_attention']
    cases=json.loads(args.cases.read_text())
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        transport=Attention(Path(tmp),config,lambda *a,**kw:None)
        for case in cases:
            path=Path(tmp)/'context.json'; path.write_text(json.dumps(case['context']))
            proc=await asyncio.create_subprocess_exec(config['command'],'--home',config['home'],
                'assess',config['backend'],str(path),'--dry-run',stdout=asyncio.subprocess.PIPE)
            stdout,_=await proc.communicate()
            if proc.returncode: raise RuntimeError('Cannot construct assessment request')
            req=json.loads(stdout)
            for order in ('original','reversed'):
                if order=='reversed':
                    for question in req['questions']: question['choices'].reverse()
                result,elapsed=await transport.evaluate(req)
                actual={a['name']:a.get('choice') for a in result['answers']}
                passed=all(actual.get(k) in options for k,options in case['expected'].items())
                rows.append({'case':case['name'],'order':order,'expected':case['expected'],
                             'actual':actual,'pass':passed,'elapsed_ms':elapsed,'result':result})
                print(json.dumps({k:rows[-1][k] for k in ('case','order','actual','pass')}),flush=True)
    summary={'policy':POLICY,'passed':sum(r['pass'] for r in rows),
             'count':len(rows),'median_ms':statistics.median(r['elapsed_ms'] for r in rows),
             'cases':rows}
    args.out.write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True)
    p.add_argument('--cases',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    asyncio.run(main(p.parse_args()))
