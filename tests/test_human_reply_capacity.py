import asyncio,contextlib,copy,hashlib,io,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import adapter
from acp_client import ProtocolError

class HumanReplyCapacity(unittest.IsolatedAsyncioTestCase):
 async def test_reserve_uses_host_social_decision_and_only_human_offer(self):
  selected=[];seen=[]
  async def request(path,payload=None):
   seen.append(path)
   if path=='/conversation/admission':return {'version':1,'remaining':1,'eligible_ids':[m['id'] for m in selected]}
   if path=='/inbox/peek':return [{'id':'peer','source':'agent'},*selected]
   if path=='/participation?human_only=1':return {'context':{'trigger_id':'h'}}
   raise AssertionError(path)
  class Attention:
   async def consider(self,request,client,*,human_only=False):
    self_outer.assertTrue(human_only);selected.append({'id':'h','source':'human','attention_offer':{'id':'offer','ticket':'opaque'}})
  self_outer=self
  async def connect():return object()
  result=await adapter.human_reply_messages(request,connect,Attention())
  self.assertEqual([m['id'] for m in result],['h']);self.assertIn('/participation?human_only=1',seen)

 async def test_full_reply_capacity_never_calls_policy_or_planner(self):
  async def request(path,payload=None):
   self.assertEqual(path,'/conversation/admission');return {'version':1,'remaining':0,'eligible_ids':['h']}
  async def connect():self.fail('No connection needed')
  self.assertEqual(await adapter.human_reply_messages(request,connect,object()),[])

 async def test_host_hold_is_applied_without_fallback_prompt(self):
  from conversation_attention import ConversationAttention,META,METHOD
  applied=[]
  class Client:
   session='same';info={'_meta':{META:{'version':1,'enabled':True,'method':METHOD}}}
   async def request(self,method,payload):
    self_outer.assertEqual(method,METHOD);return {'action':'hold','reason':'decision_budget'}
  self_outer=self
  async def request(path,payload=None):
   if path=='/conversation/admission':return {'version':1,'remaining':1,'eligible_ids':[]}
   if path=='/inbox/peek':return []
   if path=='/participation?human_only=1':return {'signature':'human-source','context':{},'occurred_at':123}
   if path=='/participation':applied.append(payload);return {'queued':False}
   raise AssertionError(path)
  async def connect():return Client()
  result=await adapter.human_reply_messages(request,connect,ConversationAttention(lambda *a,**k:None))
  self.assertEqual(result,[]);self.assertEqual(applied,[{'signature':'human-source','action':'hold','human_only':True}])

 async def test_mixed_offer_cannot_promote_peer_into_reply_reserve(self):
  offer={'id':'bound','ticket':'same'}
  async def request(path,payload=None):
   if path=='/conversation/admission':return {'version':1,'remaining':1,'eligible_ids':['human']}
   if path=='/inbox/peek':return [{'id':'human','source':'human','attention_offer':offer},{'id':'peer','source':'agent','attention_offer':offer}]
   raise AssertionError(path)
  async def connect():self.fail('Existing offer needs no re-evaluation')
  self.assertEqual(await adapter.human_reply_messages(request,connect,None),[])

 async def test_blocked_mixed_ticket_does_not_hide_independent_human_reply(self):
  offer={'id':'mixed','ticket':'same'}
  async def request(path,payload=None):
   if path=='/conversation/admission':return {'version':1,'remaining':1,'eligible_ids':['mixed-human','fresh-human']}
   if path=='/inbox/peek':return [{'id':'mixed-human','source':'human','attention_offer':offer},{'id':'peer','source':'agent','attention_offer':offer},{'id':'fresh-human','source':'human'}]
   raise AssertionError(path)
  async def connect():self.fail('Existing independent input needs no re-evaluation')
  self.assertEqual([m['id'] for m in await adapter.human_reply_messages(request,connect,None)],['fresh-human'])

 async def exercise(self,status='running',provider_failure=False,chat_only=False):
  task={'id':'original','status':status,'deadline':time.time()*1000+(-1000 if status=='budget_exhausted' else 600000),'turns':30,'max_turns':45}
  before=copy.deepcopy(task);paths=[];active=False
  message={'id':'human','source':'human','message':'What are you working on?'}
  world={'ready':True,'busy':False,'generation':7,'task':task,'conversation':{'revision':'human','messages':[]},'conversation_only':True}
  def control(cfg,path,payload=None):
   nonlocal active
   paths.append((path,payload))
   if path in ('/state','/observation'):return {**world,'turn_active':active,'pending_messages':1}
   if path=='/continuation':return {'action':'hold'}
   if path=='/conversation/admission':return {'version':1,'remaining':1,'eligible_ids':['human']}
   if path=='/inbox/peek':return [message]
   if path=='/turn':
    self.assertTrue(payload['conversation_only']);self.assertFalse(payload['renewable_lease']);active=True;return {'active':True}
   if path=='/status':return {'turn_active':active,'busy':False,'conversation_only':True}
   if path=='/conversation':return world['conversation']
   if path=='/finish':raise asyncio.CancelledError()
   if path in ('/recover','/reply'):return {}
   raise AssertionError(path)
  class Client:
   info={'agentCapabilities':{'mcpCapabilities':{'http':True}}};session='saved';active_prompt_id=None;replaying=False
   async def start(self):pass
   async def open_session(self,previous):self_outer.assertEqual(previous,'saved')
   def transport_closed(self):return False
   async def close(self):pass
   async def prompt(self,text,**kwargs):
    self_outer.assertIn('CONVERSATION-ONLY TURN',text)
    if provider_failure:raise ProtocolError('Host capacity rejected')
    return {'text':'Working on the harbor.','final_text':'Working on the harbor.','stop_reason':'end_turn','unsettled_tools':[]}
  self_outer=self
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp);cfg={'control_port':1,'token':'fixture','incoming_chat_only':chat_only};ep={'command':['unused'],'cwd':tmp};calls=[] if chat_only else [time.time()]*30
   bound={**ep,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1/mcp','headers':[{'name':'Authorization','value':'Bearer fixture'}]}]}
   for name,value in [('config',cfg),('endpoint',ep),('calls',calls),('session',{'binding':hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest(),'session':'saved'})]:
    (home/(name+'.json')).write_text(json.dumps(value))
   with patch.object(adapter,'control',control),patch.object(adapter,'Client',lambda *a:Client()),contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(adapter.run(home),2)
   self.assertEqual(json.loads((home/'calls.json').read_text()),calls)
   self.assertEqual(len(json.loads((home/'reply-calls.json').read_text())),1)
  self.assertEqual(task,before);self.assertNotIn('/turn/renew',[p for p,_ in paths])
  if chat_only:self.assertNotIn('/continuation',[p for p,_ in paths])
  self.assertEqual(any(p=='/reply' for p,_ in paths),not provider_failure)
 async def test_human_reply_passes_exhausted_construction_gate_without_task_changes(self):
  for status in ('running','budget_exhausted','stopped'):
   with self.subTest(status=status):await self.exercise(status)
 async def test_provider_rejection_is_not_bypassed_or_retried(self):await self.exercise(provider_failure=True)

 async def test_chat_only_mode_uses_reply_reserve_even_with_full_work_capacity_available(self):
  await self.exercise(status='running',chat_only=True)

 async def test_chat_only_without_human_input_does_not_poll_work_or_start_planner(self):
  seen=[]
  def control(cfg,path,payload=None):
   seen.append(path)
   if path=='/recover':return {}
   if path=='/state':return {'ready':True,'busy':False,'turn_active':False,'task':{'status':'running'}}
   if path=='/conversation/admission':return {'version':1,'remaining':12,'eligible_ids':[]}
   if path=='/inbox/peek':return [{'source':'agent','id':'peer'}]
   raise AssertionError(path)
  async def stop_after_idle(seconds):
   self.assertEqual(seconds,2);raise asyncio.CancelledError()
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp)
   (home/'config.json').write_text(json.dumps({'incoming_chat_only':True,'control_port':1,'token':'fixture'}))
   (home/'endpoint.json').write_text(json.dumps({'command':['unused'],'cwd':tmp}))
   with patch.object(adapter,'control',control),patch.object(adapter,'Client',side_effect=AssertionError('No planner needed')),patch.object(adapter.asyncio,'sleep',stop_after_idle):
    with self.assertRaises(asyncio.CancelledError):await adapter.run(home)
  self.assertNotIn('/continuation',seen);self.assertNotIn('/turn',seen);self.assertNotIn('/watch-context',seen)
