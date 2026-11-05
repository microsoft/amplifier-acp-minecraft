import sys,unittest
from pathlib import Path
from acp_client import Client
class Revisions(unittest.IsolatedAsyncioTestCase):
 async def result(self,mode):
  c=Client({'command':[sys.executable,str(Path(__file__).with_name('output_fixture.py')),mode],'cwd':'/tmp'},lambda *a,**k:None)
  try:
   await c.start();await c.open_session();return await c.prompt('Existing work',5)
  finally:await c.close()
 async def test_latest_created_answer_wins_despite_interleaved_older_chunks_and_commentary(self):
  result=await self.result('revision')
  self.assertEqual(result['final_text'],'Sticks already delivered.')
  self.assertIn('Need sticks.',result['text'])
 async def test_empty_final_revision_stays_silent_without_replaying_a_draft(self):
  self.assertEqual((await self.result('silence'))['final_text'],'')
 async def test_unidentified_acp_text_keeps_legacy_append_behavior(self):
  self.assertEqual((await self.result('legacy'))['final_text'],'One plain answer.')
