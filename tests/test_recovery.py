import asyncio,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from acp_client import Client,ProtocolError

FIXTURE=Path(__file__).with_name('replay_fixture.py')
class Replay(unittest.IsolatedAsyncioTestCase):
 async def test_progressing_replay_has_separate_total_and_idle_deadlines(self):
  c=Client({'command':[sys.executable,str(FIXTURE),'progress'],'cwd':'/tmp'},lambda *a,**k:None,load_timeout=1,idle_timeout=.1)
  try:
   await c.start();self.assertEqual(await c.open_session('saved'),'saved')
  finally:await c.close()
 async def test_replay_stall_and_total_timeout_are_distinct(self):
  for scenario,total,idle,pattern in [('stall',1,.05,'stopped making'),('progress',.08,.1,'total replay')]:
   c=Client({'command':[sys.executable,str(FIXTURE),scenario],'cwd':'/tmp'},lambda *a,**k:None,load_timeout=total,idle_timeout=idle)
   try:
    await c.start()
    with self.assertRaisesRegex(ProtocolError,pattern):await c.open_session('saved')
   finally:await c.close()
 async def test_no_silent_replacement_of_saved_session(self):
  c=Client({'command':[sys.executable,str(FIXTURE),'no-load'],'cwd':'/tmp'},lambda *a,**k:None)
  try:
   await c.start()
   with self.assertRaisesRegex(ProtocolError,'refusing to replace'):await c.open_session('saved')
  finally:await c.close()
 async def test_load_never_grants_permissions(self):
  c=Client({'command':[sys.executable,str(FIXTURE),'permission'],'cwd':'/tmp'},lambda *a,**k:None)
  try:
   await c.start();c.permission_active=lambda:True;await c.open_session('saved')
  finally:await c.close()
