"""Actual controller loop: recovery inspection is independent of work authority."""
import asyncio,contextlib,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import adapter

class RecoveryScheduling(unittest.IsolatedAsyncioTestCase):
 async def exercise(self, optional_offer=False):
  recovered=optional_offer;paths=[];reservations=[]
  def control(cfg,path,payload=None):
   nonlocal recovered
   paths.append(path)
   if path=='/recover':return {}
   if path=='/state':return {'ready':True,'generation':1,'task':{'id':'same','status':'running' if recovered else 'needs_review'},'task_capabilities':{'autonomous_work_allowed':recovered,'recovery_review_allowed':not recovered}}
   if path=='/continuation':recovered=True;return {'action':'inspect_then_continue'}
   if path=='/conversation/admission':return {'version':1,'unmetered':True,'eligible_ids':[]}
   if path=='/inbox/peek':return [{'id':'peer','source':'agent','attention_offer':{'id':'offered','ticket':'unchanged'}}] if optional_offer else []
   if path=='/turn':reservations.append(payload);raise asyncio.CancelledError()
   raise AssertionError(path)
  class Client:
   info={'agentCapabilities':{'mcpCapabilities':{'http':True}}};session='saved'
   async def start(self):pass
   async def open_session(self,previous):assert previous=='saved'
   async def close(self):pass
   def transport_closed(self):return False
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp);cfg={'control_port':1,'token':'fixture','incoming_chat_only':True,'human_engagement':{'enabled':True},'human_task_intake':{'enabled':True}}
   endpoint={'command':['unused'],'cwd':tmp};bound={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1/mcp','headers':[{'name':'Authorization','value':'Bearer fixture'}]}]}
   for name,value in [('config',cfg),('endpoint',endpoint),('session',{'binding':hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest(),'session':'saved'})]:
    (home/(name+'.json')).write_text(json.dumps(value))
   with patch.object(adapter,'control',control),patch.object(adapter,'Client',lambda *a:Client()),contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(adapter.run(home),2)
  self.assertEqual(paths.count('/continuation'),1)
  self.assertEqual(len(reservations),1)
  self.assertTrue(reservations[0]['continuation'])
  self.assertFalse(reservations[0]['conversation_only'])
  self.assertEqual(reservations[0]['message_ids'],[])

 async def test_recovery_refreshes_authority_before_reserving_work(self):
  await self.exercise()

 async def test_ineligible_optional_offer_does_not_block_or_enter_task_prompt(self):
  await self.exercise(optional_offer=True)
