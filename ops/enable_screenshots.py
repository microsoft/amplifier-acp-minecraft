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
a=p.parse_args();original_config=a.config.read_bytes();config=json.loads(original_config);directory=a.directory.expanduser().resolve()
if not a.node:p.error('Node executable is required')
app=a.app.resolve(strict=True);node=a.node.resolve(strict=True)
browser=a.browser_path or (config.get('screenshots') or {}).get('browser_path')
browser=Path(browser).expanduser().resolve(strict=True) if browser else None
command=[str(node),str(app/'screenshot-browser.cjs'),'prepare']
if browser:command+=['--browser-path',str(browser)]
# Fail before writing config if browser installation, launch or graphics fail.
subprocess.run(command,cwd=app,check=True,timeout=360)
if a.config.read_bytes()!=original_config:raise SystemExit('Configuration changed during browser setup; inspect and rerun without overwriting it')
directory.mkdir(parents=True,exist_ok=True,mode=0o700)
config['screenshots']={'enabled':True,'directory':str(directory)}
if browser:config['screenshots']['browser_path']=str(browser)
tmp=a.config.with_name(a.config.name+'.new');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out:json.dump(config,out,indent=2);out.write('\n')
os.replace(tmp,a.config)
print(json.dumps({'screenshots':config['screenshots'],'next':'Restart the body at an idle boundary; tasks and budgets are unchanged.'},indent=2))
