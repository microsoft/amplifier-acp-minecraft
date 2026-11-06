import json,sys,time
scenario=sys.argv[1]
def send(value):print(json.dumps({'jsonrpc':'2.0',**value}),flush=True)
for line in sys.stdin:
 v=json.loads(line);method=v.get('method')
 if method=='initialize':send({'id':v['id'],'result':{'protocolVersion':1,'agentCapabilities':{'loadSession':scenario!='no-load'}}})
 elif method=='session/load':
  if scenario=='stall':time.sleep(.3)
  if scenario=='progress':
   for i in range(6):
    time.sleep(.03);send({'method':'session/update','params':{'sessionId':'saved','update':{'sessionUpdate':'user_message_chunk','content':{'type':'text','text':'archived'}}}})
  if scenario=='permission':
   send({'id':'permission','method':'session/request_permission','params':{'sessionId':'saved','toolCall':{'toolCallId':'replay','rawInput':{'server':'minecraft','tool':'move'}},'options':[{'name':'Permission','kind':'allow_once','optionId':'allow'}]}})
   response=json.loads(sys.stdin.readline());assert response['result']['outcome']['outcome']=='cancelled'
  send({'id':v['id'],'result':{}})
 else:send({'id':v['id'],'error':{'code':-32601,'message':'unsupported'}})
