import asyncio,json,sys,tempfile,unittest
from pathlib import Path
from acp_client import Client,ProtocolError
from maintenance import compact
from harness_capabilities import MAINTENANCE_META

IDLE={'ready':True,'busy':False,'turn_active':False,'action_lease':{'version':1,'lease_id':None,'renewable':False}}
class Maintenance(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,mode,expected,exception=None):
        with tempfile.TemporaryDirectory() as tmp:
            events=[];status_calls=[]
            c=Client({'command':[sys.executable,str(Path(__file__).with_name('maintenance_fixture.py')),tmp,mode],'cwd':tmp},lambda k,**v:events.append((k,v)))
            async def status():status_calls.append(True);return dict(IDLE)
            try:
                await c.start();await c.open_session()
                if exception:
                    with self.assertRaises(exception):await compact(c,tmp,'stable-operation',status,timeout=.1 if mode=='no-terminal' else 2)
                else:
                    result=await compact(c,tmp,'stable-operation',status,timeout=2)
                    self.assertEqual(result['status'],expected)
                files=list((Path(tmp)/'maintenance-receipts').glob('*.json'))
                if expected is not None:self.assertEqual(json.loads(files[0].read_text())['status'],expected)
                frames=[json.loads(line) for line in (Path(tmp)/'frames.jsonl').read_text().splitlines()]
                prompts=[f for f in frames if f.get('method')=='session/prompt']
                self.assertEqual(len(prompts),0 if expected is None else 1)
                if prompts:
                    self.assertEqual(prompts[0]['params']['prompt'],[{'type':'text','text':'/compact'}])
                    self.assertEqual(prompts[0]['params']['_meta'][MAINTENANCE_META]['operationId'],'stable-operation')
                if expected=='completed':
                    self.assertEqual(len(status_calls),2)
                    self.assertEqual(c.session,'original-session')
                    self.assertTrue(any(k=='permission_cancelled' for k,v in events))
                    with self.assertRaises(FileExistsError):await compact(c,tmp,'stable-operation',status)
                    self.assertEqual(json.loads(files[0].read_text())['status'],'completed')
                self.assertFalse(c.maintenance_active)
            finally:await c.close()
    async def test_bare_command_both_signals_closed_authority_and_callback_denial(self):await self.exercise('success','completed')
    async def test_other_compaction_completion_is_not_success(self):await self.exercise('unrelated','unknown')
    async def test_compaction_success_without_terminal_times_out_unknown(self):await self.exercise('no-terminal','unknown',asyncio.TimeoutError)
    async def test_transport_loss_is_unknown_not_replayed(self):await self.exercise('closed','unknown',ProtocolError)
    async def test_no_capability_never_falls_back_to_model_prompt(self):await self.exercise('no-capability',None,ValueError)
    async def test_no_advertised_command_never_falls_back_to_model_prompt(self):await self.exercise('no-command',None,ValueError)
    async def test_failed_postcheck_closes_connection_and_keeps_unknown_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Client({'command':[sys.executable,str(Path(__file__).with_name('maintenance_fixture.py')),tmp,'success'],'cwd':tmp},lambda *a,**k:None)
            calls=0
            async def status():
                nonlocal calls
                calls+=1
                if calls>1:raise OSError('body unavailable')
                return dict(IDLE)
            try:
                await c.start();await c.open_session()
                with self.assertRaises(OSError):await compact(c,tmp,'postcheck',status,timeout=2)
                self.assertTrue(c.transport_closed())
                receipt=json.loads(next((Path(tmp)/'maintenance-receipts').glob('*.json')).read_text())
                self.assertEqual(receipt['status'],'unknown')
                self.assertTrue(receipt['prompt_terminal'])
            finally:await c.close()
    async def test_active_body_or_prompt_cannot_enter_maintenance(self):
        c=Client({},lambda *a,**k:None);c.info={'_meta':{'io.github.bkrabach.agent-instance':{'maintenance':{'version':1,'promptMetadata':MAINTENANCE_META,'requiresAdvertisedCommand':True}}}}
        c.session='s';c.available_commands={'s':{'compact'}}
        async def active():return {**IDLE,'turn_active':True}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):await compact(c,tmp,'no-send',active)
            self.assertFalse((Path(tmp)/'maintenance-receipts').exists())
            c.active_prompt_id=7
            with self.assertRaises(ValueError):await compact(c,tmp,'no-send',active)
            c.maintenance_active=True
            with self.assertRaises(ProtocolError):await c.prompt('No competing work')
            self.assertEqual(c.next_id,0)
