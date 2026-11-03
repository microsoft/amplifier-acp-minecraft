import argparse,json
from pathlib import Path
from adapter import control
p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--reviewer',action='append',default=[]);p.add_argument('operation',choices=['state','task','stop']);p.add_argument('text',nargs='?');a=p.parse_args()
cfg=json.loads((a.home.expanduser()/'config.json').read_text())
payload={'text':a.text,'reviewers':a.reviewer} if a.operation=='task' else {} if a.operation=='stop' else None
print(json.dumps(control(cfg,'/'+a.operation,payload),indent=2))
