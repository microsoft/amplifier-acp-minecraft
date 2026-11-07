"""Optional same-host Instance context registration; no model/session priming."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_registration import registration
from installation_guard import durable_write


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--agent-home',type=Path)
    parser.add_argument('--stage-only',action='store_true',help='Write private pending configuration only; no Instance requests or starts')
    args=parser.parse_args(argv)
    os.umask(0o077)
    home=args.home.expanduser().resolve();cfg=json.loads((home/'config.json').read_text())
    if args.stage_only:
        # The installation chooses its stable identity; a username alone cannot
        # distinguish two worlds. Never silently generate/reassign that identity.
        if not cfg.get('context_provider_id'):
            raise ValueError('Set a unique context_provider_id for this connection before staging')
        cfg.setdefault('context_token',secrets.token_urlsafe(32))
        cfg.setdefault('context_grant',secrets.token_urlsafe(32))
        plan=registration(cfg,[])
        durable_write(home/'config.json',cfg)
        durable_write(home/'pending-context-registration.json',{
            'provider':plan['provider'],'status':'pending_actual_route_verification'})
        print('Staged only. Start this connection body, verify its actual runtime namespace route, then register it.')
        return
    if not args.agent_home:raise ValueError('--agent-home is required for verified registration')
    agent=args.agent_home.expanduser().resolve()
    def api(method,path,body=None):
        command=[str(agent/'bin/agent-instance'),'--home',str(agent),'api',method,path]
        with tempfile.TemporaryDirectory() as directory:
            if body is not None:
                p=Path(directory)/'body.json';durable_write(p,body);command+=['--file',str(p)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            if result.returncode:raise RuntimeError('Instance management request failed: '+path)
            return json.loads(result.stdout)
    providers=api('GET','context/providers')['providers']
    plan=registration(cfg,providers)
    request=urllib.request.Request(plan['provider']['url']+'/context/v1/query',
        data=json.dumps({'operation':'orientation','access':{'mode':'owner'}}).encode(),
        headers={'Authorization':'Bearer '+cfg['context_token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=10) as response:context=json.load(response)
    if context.get('current',{}).get('activity',{}).get('connected') is not True:
        raise RuntimeError('Body context is not connected; no Instance registration changed')
    if api('GET','context/providers')['providers'] != providers:
        raise RuntimeError('Providers changed concurrently; inspect before retrying')
    api('PUT','secrets/'+plan['secret_ref'],{'value':cfg['context_token']})
    api('PUT','context/providers',{'providers':plan['providers']})
    after=api('GET','context/providers')['providers']
    public=[{k:v for k,v in p.items() if k in ('id','label','url','secret_ref')} for p in after]
    if sorted(public,key=lambda p:p['id']) != sorted(plan['providers'],key=lambda p:p['id']):
        raise RuntimeError('Registration readback differs; inspect instead of replaying')
    durable_write(home/'context-registration-receipt.json',{
        'provider':plan['provider'],'verified':'same-host authenticated context and registration readback',
        'runtime_namespace_verified':False,'model_prompt':False,'session_created':False})
    print('Registered this connection; other provider entries and secrets preserved. Verify any separate runtime/container route before starting its controller.')


if __name__=='__main__':main()
