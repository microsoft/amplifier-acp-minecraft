"""Disposable candidate-contract peer. No model or game connection."""
import json,sys
from pathlib import Path
directory,mode=Path(sys.argv[1]),sys.argv[2]
sid='original-session';active=None;operation=None
META='com.microsoft.amplifier.maintenance'
def send(v):print(json.dumps({'jsonrpc':'2.0',**v}),flush=True)
def update(v):send({'method':'session/update','params':{'sessionId':sid,'update':v}})
def finish():
    update({'sessionUpdate':'compaction_update','compactionId':'other' if mode=='unrelated' else 'one','status':'completed'})
    if mode=='no-terminal':return
    send({'id':active,'result':{'stopReason':'end_turn','_meta':{META:{'version':1,'operation':'compact','operationId':operation,
        'sessionId':sid,'compactionId':'one','status':'completed'}}}})
for line in sys.stdin:
    v=json.loads(line)
    with (directory/'frames.jsonl').open('a') as f:f.write(json.dumps(v)+'\n')
    method=v.get('method')
    if method=='initialize':
        send({'id':v['id'],'result':{'protocolVersion':1,'agentCapabilities':{'loadSession':True},'_meta':{} if mode=='no-capability' else {
            'io.github.bkrabach.agent-instance':{'maintenance':{'version':1,'promptMetadata':META,'requiresAdvertisedCommand':True}}}}})
    elif method=='session/new':
        update({'sessionUpdate':'available_commands_update','availableCommands':[] if mode=='no-command' else [{'name':'compact','description':'Compact'}]})
        send({'id':v['id'],'result':{'sessionId':sid}})
    elif method=='session/prompt':
        active=v['id'];operation=v['params']['_meta'][META]['operationId']
        assert v['params']['prompt']==[{'type':'text','text':'/compact'}]
        update({'sessionUpdate':'compaction_update','compactionId':'one','status':'in_progress'})
        if mode=='closed':sys.exit(0)
        send({'id':'permission','method':'session/request_permission','params':{'sessionId':sid,
            'toolCall':{'toolCallId':'mutation','rawInput':{'server':'minecraft','tool':'place'}},
            'options':[{'kind':'allow_once','optionId':'once'}]}})
    elif v.get('id')=='permission':
        assert v['result']['outcome']=={'outcome':'cancelled'}
        finish()
    elif method=='session/cancel':
        send({'id':active,'result':{'stopReason':'cancelled'}})
