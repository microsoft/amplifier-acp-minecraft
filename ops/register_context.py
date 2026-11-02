"""Optional Agent Instance context registration; the game/ACP core needs no management API."""
import argparse,json,os,secrets,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--agent-home',type=Path,required=True);a=p.parse_args()
home=a.home.expanduser();agent=a.agent_home.expanduser();cfg=json.loads((home/'config.json').read_text())
# This helper installs a same-machine loopback source. Remote deployments require
# a trusted HTTPS endpoint and their own scoped provisioning.
cfg.setdefault('context_token',secrets.token_urlsafe(32));cfg.setdefault('context_grant',secrets.token_urlsafe(32))
cfg.setdefault('context_provider_id','minecraft:'+cfg['username'].lower());cfg.setdefault('conversation_id','minecraft:workshop')
tmp=home/'config.json.tmp';tmp.write_text(json.dumps(cfg,indent=2));os.chmod(tmp,0o600);tmp.replace(home/'config.json')
def api(method,path,body=None):
 cmd=[str(agent/'bin/agent-instance'),'--home',str(agent),'api',method,path]
 with tempfile.TemporaryDirectory() as d:
  if body is not None:
   f=Path(d)/'body.json';f.write_text(json.dumps(body));os.chmod(f,0o600);cmd+=['--file',str(f)]
  result=subprocess.run(cmd,capture_output=True,text=True)
  if result.returncode:raise RuntimeError('Agent Instance management request failed: '+path)
  return json.loads(result.stdout)
secret='minecraft-'+cfg['username'].lower()+'-context'
api('PUT','secrets/'+secret,{'value':cfg['context_token']})
providers=api('GET','context/providers')['providers']
providers=[{k:v for k,v in r.items() if k in ('id','label','url','secret_ref')} for r in providers if r['id']!=cfg['context_provider_id']]
providers.append({'id':cfg['context_provider_id'],'label':'Minecraft — '+cfg['username'],'url':f"http://127.0.0.1:{cfg['control_port']}",'secret_ref':secret})
api('PUT','context/providers',{'providers':providers})
print('Registered Minecraft context and shared-room session binding. Restart this player body and controller to apply.')
