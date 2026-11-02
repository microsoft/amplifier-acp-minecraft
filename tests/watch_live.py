"""Live replay of agent-authored watches. No game mutations or planner calls."""
import argparse,asyncio,copy,json,statistics,tempfile,time
from pathlib import Path
from attention import Attention


async def local(runtime,store,envelope):
    file=store.with_suffix('.input.json');file.write_text(json.dumps(envelope));file.chmod(0o600)
    p=await asyncio.create_subprocess_exec(str(runtime),'watch','--store',str(store),str(file),
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    out,err=await p.communicate()
    if p.returncode:raise RuntimeError(err.decode())
    return json.loads(out)


async def main(a):
    cfg=json.loads((a.home/'config.json').read_text())['decision_attention']
    rows=[];policy=None
    with tempfile.TemporaryDirectory() as tmp:
        temp=Path(tmp);transport=Attention(temp,cfg,lambda *a,**kw:None)
        for case in json.loads(a.cases.read_text()):
            for order in ('original','reversed'):
                store=temp/(case['name']+'-'+order+'.json')
                env={'scope':'replay','task':{'id':'test','goal':case['goal'],'status':'waiting',
                    'deadline_ms':int(time.time()*1000)+600000,'remaining_turns':10},'events':[]}
                trigger={'any_of':case['any_of']} if 'any_of' in case else {'condition':case['condition']}
                env['action']={'operation':'arm','spec':{'label':case['name'],**trigger,
                    'kinds':case.get('kinds',['message']),'ttl_seconds':300}}
                await local(a.runtime,store,env)
                env['events']=case['events'];env['action']={'operation':'prepare'}
                prepared=await local(a.runtime,store,env)
                if prepared.get('policy'):policy=prepared['policy']
                if 'request' not in prepared:
                    rows.append({'case':case['name'],'order':order,'wake':False,'pass':not case['wake'],'skipped':prepared['skip']});continue
                req=copy.deepcopy(prepared['request'])
                if order=='reversed':
                    for q in req['questions']:q['choices'].reverse()
                result,elapsed=await transport.evaluate(req)
                env['action']={'operation':'resolve','token':prepared['token'],'result':result}
                resolved=await local(a.runtime,store,env)
                wake=any(r.get('wake') for r in resolved['receipts'])
                branch_wakes=[x.get('choice')=='wake' and x.get('probabilities',{}).get('wake',0)>=0.5 for x in result['answers']]
                passed=wake==case['wake'] and ('branch_wakes' not in case or branch_wakes==case['branch_wakes'])
                row={'case':case['name'],'order':order,'expected_wake':case['wake'],'wake':wake,'branch_wakes':branch_wakes,'pass':passed,
                     'elapsed_ms':elapsed,'request':req,'result':result,'receipts':resolved['receipts']}
                rows.append(row);print(json.dumps({k:row[k] for k in ('case','order','wake','pass','elapsed_ms')}),flush=True)
    summary={'policy':policy,'passed':sum(r['pass'] for r in rows),'count':len(rows),
             'median_ms':statistics.median(r['elapsed_ms'] for r in rows if 'elapsed_ms' in r),'cases':rows}
    a.out.write_text(json.dumps(summary,indent=2));a.out.chmod(0o600)
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--home',type=Path,required=True)
    p.add_argument('--cases',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    asyncio.run(main(p.parse_args()))
