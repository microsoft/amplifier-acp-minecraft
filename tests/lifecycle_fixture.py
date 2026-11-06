"""Disposable ACP endpoint: no provider, Minecraft connection or external effects."""
import json
from pathlib import Path
import sys
import time

home=Path(sys.argv[1]);scenario=sys.argv[2]
def send(value):print(json.dumps({'jsonrpc':'2.0',**value}),flush=True)
for line in sys.stdin:
    value=json.loads(line);method=value['method']
    with (home/'frames.jsonl').open('a') as out:out.write(json.dumps(value)+'\n')
    if method=='initialize':
        assert value['params']['clientCapabilities']['session']['compaction']=={}
        send({'id':value['id'],'result':{'protocolVersion':1,'agentCapabilities':{}}})
    elif method=='session/new':send({'id':value['id'],'result':{'sessionId':'same-session'}})
    elif method=='session/prompt':
        def update(status):send({'method':'session/update','params':{'sessionId':'same-session','update':{'sessionUpdate':'compaction_update','compactionId':'cmp','status':status}}})
        update('in_progress')
        if scenario=='closed':sys.exit(0)
        update('completed')
        while not (home/'terminal').exists():time.sleep(.005)
        send({'id':value['id'],'result':{'stopReason':'end_turn'}})
