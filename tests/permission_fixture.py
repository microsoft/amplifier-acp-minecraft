import json,sys
scenario=sys.argv[1]
def send(v):print(json.dumps({'jsonrpc':'2.0',**v}),flush=True)
for line in sys.stdin:
 v=json.loads(line);m=v.get('method')
 if m=='initialize':send({'id':v['id'],'result':{'protocolVersion':1,'agentCapabilities':{'mcpCapabilities':{'http':True}}}})
 elif m=='session/new':send({'id':v['id'],'result':{'sessionId':'test-session'}})
 elif m=='session/prompt':
  supplied_prompt=v['params']['prompt']
  if scenario=='narration':send({'method':'session/update','params':{'sessionId':'test-session','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'I will inspect first.'}}}})
  raw={'server':'minecraft','tool':'observe','arguments':{}}
  if scenario.startswith('game:'):raw['tool']=scenario.split(':',1)[1]
  if scenario=='external':raw={'server':'filesystem','tool':'delete','arguments':{}}
  send({'method':'session/update','params':{'sessionId':'test-session','update':{'sessionUpdate':'tool_call','toolCallId':'t1','title':'mcp.minecraft.observe','rawInput':raw}}})
  send({'id':90,'method':'session/request_permission','params':{'sessionId':'wrong' if scenario=='wrong_session' else 'test-session','toolCall':{'toolCallId':'t1'},'options':[{'kind':'allow_always','optionId':'forever'},{'kind':'allow_once','optionId':'once'}]}})
  reply=json.loads(sys.stdin.readline())
  result=reply['result']
  if scenario=='context':result['supplied_prompt']=supplied_prompt
  send({'method':'session/update','params':{'sessionId':'test-session','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':json.dumps(result)}}}})
  send({'id':v['id'],'result':{'stopReason':'end_turn'}})
