"""Independent ACP peer exercising the real adapter/MCP continuation contract."""
import json,sys,urllib.request
url=token=None;turn=0
def send(value):print(json.dumps({'jsonrpc':'2.0',**value}),flush=True)
def tool(name,arguments):
 req=urllib.request.Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}}).encode(),headers={'Authorization':token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
 result=json.load(urllib.request.urlopen(req))['result'];assert not result.get('isError'),result
 return json.loads(result['content'][0]['text'])
for line in sys.stdin:
 v=json.loads(line);method=v.get('method')
 if method=='initialize':send({'id':v['id'],'result':{'protocolVersion':1,'agentCapabilities':{'mcpCapabilities':{'http':True}}}})
 elif method=='session/new':
  server=v['params']['mcpServers'][0];url=server['url'];token=server['headers'][0]['value'];send({'id':v['id'],'result':{'sessionId':'work-fixture'}})
 elif method=='session/prompt':
  turn+=1
  if turn==1:
   state=tool('observe',{});request=next(e for e in reversed(state['events']) if e['kind']=='chat' and e.get('accepted'))
   tool('work_begin',{'request_id':request['id'],'goal':'fixture two-turn task'})
  tool('work_report',{'status':'running' if turn==1 else 'review','summary':f'Fixture turn {turn} completed'})
  send({'id':v['id'],'result':{'stopReason':'end_turn'}})
