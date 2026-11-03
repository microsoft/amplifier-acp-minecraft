import json,sys,unittest
from pathlib import Path
from acp_client import Client
class Permissions(unittest.IsolatedAsyncioTestCase):
 async def check(self,scenario,active=True):
  c=Client({'command':[sys.executable,str(Path(__file__).with_name('permission_fixture.py')),scenario],'cwd':'/tmp'},lambda *a,**kw:None)
  try:
   await c.start();await c.open_session();c.permission_active=lambda:active
   return json.loads((await c.prompt('test',5))['text'])['outcome']
  finally:await c.close()
 async def test_only_game_tool_once(self):self.assertEqual(await self.check('game'),{'outcome':'selected','optionId':'once'})
 async def test_display_title_does_not_authorize_other_server(self):self.assertEqual((await self.check('external'))['outcome'],'cancelled')
 async def test_wrong_session_denied(self):self.assertEqual((await self.check('wrong_session'))['outcome'],'cancelled')
 async def test_stopped_turn_denied(self):self.assertEqual((await self.check('game',False))['outcome'],'cancelled')
 async def test_survival_tools_use_same_scoped_permission_boundary(self):
  for tool in ('entities','shear','furnace','container','attention_watch','attention_watches','attention_cancel','read_sign','write_sign'):
   self.assertEqual(await self.check('game:'+tool),{'outcome':'selected','optionId':'once'})
   self.assertEqual((await self.check('game:'+tool,False))['outcome'],'cancelled')

 async def test_final_reply_excludes_pre_tool_narration(self):
  c=Client({'command':[sys.executable,str(Path(__file__).with_name('permission_fixture.py')),'narration'],'cwd':'/tmp'},lambda *a,**kw:None)
  try:
   await c.start();await c.open_session();c.permission_active=lambda:True
   result=await c.prompt('test',5)
   self.assertIn('I will inspect first.',result['text'])
   self.assertNotIn('I will inspect first.',result['final_text'])
   self.assertEqual(json.loads(result['final_text'])['outcome']['outcome'],'selected')
  finally:await c.close()
