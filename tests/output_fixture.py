import json,sys
mode=sys.argv[1]
def emit(v):print(json.dumps({'jsonrpc':'2.0',**v}),flush=True)
for line in sys.stdin:
 r=json.loads(line);method=r.get('method')
 if method=='initialize':result={'protocolVersion':1}
 elif method=='session/new':result={'sessionId':'output-test'}
 elif method=='session/prompt':
  updates=[('draft','Need sticks.','final_answer'),('new','Sticks already ','final_answer'),('draft',' Please send some.','final_answer'),('new','delivered.','final_answer'),('status','Checking receipts.','commentary')]
  if mode=='silence':updates.append(('silent','','final_answer'))
  if mode=='legacy':updates=[(None,'One ',None),(None,'plain answer.',None)]
  for ident,text,phase in updates:
   update={'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':text}}
   if ident:update['messageId']=ident
   if phase:update['_meta']={'com.microsoft.amplifier.message':{'phase':phase}}
   emit({'method':'session/update','params':{'sessionId':'output-test','update':update}})
  result={'stopReason':'end_turn'}
 else:result={}
 emit({'id':r['id'],'result':result})
