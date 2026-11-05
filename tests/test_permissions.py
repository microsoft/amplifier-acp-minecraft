import json,sys,unittest
from pathlib import Path
from acp_client import Client, GAME_TOOLS
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

 async def test_every_advertised_tool_matches_actual_permission_callback(self):
  c=Client({},lambda *a,**k:None);c.session='test-session';c.permission_active=lambda:True
  context=c.permission_context()
  self.assertTrue(context['active']);self.assertIn('container',context['allow_once_tools'])
  self.assertEqual(set(context['allow_once_tools']),GAME_TOOLS)
  for tool in context['allow_once_tools']:
   self.assertEqual(await self.check('game:'+tool),{'outcome':'selected','optionId':'once'})
  self.assertEqual((await self.check('game:execute_admin'))['outcome'],'cancelled')

 async def test_snapshot_cannot_authorize_a_later_stopped_turn_or_replay(self):
  c=Client({},lambda *a,**k:None);c.session='test-session';c.permission_active=lambda:True
  active=c.permission_context();c.permission_active=lambda:False
  stopped=c.permission_context();self.assertFalse(stopped['active']);self.assertEqual(stopped['allow_once_tools'],[])
  self.assertEqual(active['policy_revision'],stopped['policy_revision'])
  self.assertEqual((await self.check('game:container',False))['outcome'],'cancelled')
  c.permission_active=lambda:True;c.replaying=True
  self.assertFalse(c.permission_context()['active']);self.assertEqual(c.permission_context()['allow_once_tools'],[])
  c.replaying=False;c.session=None;self.assertFalse(c.permission_context()['active'])

 async def test_prompt_supplies_current_policy_without_replacing_task_or_binding(self):
  events=[]
  c=Client({'command':[sys.executable,str(Path(__file__).with_name('permission_fixture.py')),'context'],'cwd':'/tmp'},lambda *a,**kw:events.append((a,kw)))
  try:
   await c.start();await c.open_session();c.permission_active=lambda:True;session=c.session
   result=json.loads((await c.prompt('Continue unchanged accepted task',5))['text'])
   blocks=result['supplied_prompt'];self.assertEqual(len(blocks),2)
   snapshot=json.loads(blocks[0]['text'].splitlines()[1])
   self.assertTrue(snapshot['active']);self.assertIn('container',snapshot['allow_once_tools'])
   self.assertEqual(blocks[1]['text'],'Continue unchanged accepted task');self.assertEqual(c.session,session)
   self.assertTrue(any(a==('permission_context_supplied',) for a,k in events))
  finally:await c.close()

 async def test_stop_after_snapshot_still_cancels_callback(self):
  c=Client({'command':[sys.executable,str(Path(__file__).with_name('permission_fixture.py')),'context'],'cwd':'/tmp'},lambda *a,**kw:None)
  try:
   await c.start();await c.open_session();states=iter([True,False]);c.permission_active=lambda:next(states)
   result=json.loads((await c.prompt('Existing task',5))['text'])
   self.assertTrue(json.loads(result['supplied_prompt'][0]['text'].splitlines()[1])['active'])
   self.assertEqual(result['outcome'],{'outcome':'cancelled'})
  finally:await c.close()

 async def test_final_reply_excludes_identified_commentary_before_tool(self):
  c=Client({'command':[sys.executable,str(Path(__file__).with_name('permission_fixture.py')),'narration'],'cwd':'/tmp'},lambda *a,**kw:None)
  try:
   await c.start();await c.open_session();c.permission_active=lambda:True
   result=await c.prompt('test',5)
   self.assertIn('I will inspect first.',result['text'])
   self.assertNotIn('I will inspect first.',result['final_text'])
   self.assertEqual(json.loads(result['final_text'])['outcome']['outcome'],'selected')
  finally:await c.close()
