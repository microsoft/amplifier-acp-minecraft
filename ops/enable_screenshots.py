#!/usr/bin/env python3
"""Enable local player captures. Install/build the optional renderer first.
Does not restart the player, change tasks, or grant upload/network authority.
"""
import argparse,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--config',type=Path,required=True)
p.add_argument('--directory',type=Path,required=True,help='Prefer screenshots/minecraft inside this agent’s granted workspace')
p.add_argument('--browser-path',type=Path)
p.add_argument('--node',type=Path,default=shutil.which('node'))
p.add_argument('--app',type=Path,default=Path(__file__).resolve().parents[1],help='Installed adapter source with locked dependencies')
a=p.parse_args();config=json.loads(a.config.read_text());directory=a.directory.expanduser().resolve()
if not a.node:p.error('Node executable is required')
app=a.app.resolve(strict=True);node=a.node.resolve(strict=True)
command=[str(node),str(app/'screenshot-browser.cjs'),'prepare']
if a.browser_path:command+=['--browser-path',str(a.browser_path.expanduser().resolve(strict=True))]
# Fail before writing config if browser installation, launch or graphics fail.
subprocess.run(command,cwd=app,check=True,timeout=360)
directory.mkdir(parents=True,exist_ok=True,mode=0o700)
config['screenshots']={'enabled':True,'directory':str(directory)}
if a.browser_path:config['screenshots']['browser_path']=str(a.browser_path.expanduser().resolve(strict=True))
tmp=a.config.with_name(a.config.name+'.new');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out:json.dump(config,out,indent=2);out.write('\n')
os.replace(tmp,a.config)
print(json.dumps({'screenshots':config['screenshots'],'next':'Restart the body at an idle boundary; tasks and budgets are unchanged.'},indent=2))
