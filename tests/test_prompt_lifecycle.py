import asyncio
import unittest
from prompt_lifecycle import PromptLifecycle
from acp_client import Client

class Lifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_transport_write_is_bounded_without_replay_or_settlement_claim(self):
        c=Client({},lambda *a,**k:None);c.session='same';sent=[]
        async def blocked_send(frame):
            sent.append(frame)
            await asyncio.Event().wait()
        c.send=blocked_send
        with self.assertRaises(asyncio.TimeoutError):await c.cancel(timeout=.01)
        self.assertEqual(sent,[{'method':'session/cancel','params':{'sessionId':'same'}}])

    def test_silence_and_repeated_metadata_are_unknown_not_failure_or_progress(self):
        now=[0]; events=[]
        p=PromptLifecycle(lambda kind,**fields:events.append((kind,fields)),clock=lambda:now[0])
        now[0]=221
        p.update({'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':''}})
        p.update({'sessionUpdate':'usage_update','used':123})
        self.assertTrue(p.sample()['quiet']);self.assertEqual(p.last_progress,0)
        self.assertFalse(events[-1][1]['cancelled']);self.assertEqual(events[-1][1]['provider_health'],'unknown')
        p.sample();self.assertEqual(len(events),1)
        p.update({'sessionUpdate':'agent_message_chunk','content':{'text':'Actual progress'}})
        self.assertFalse(p.sample()['quiet']);self.assertEqual(events[-1][0],'planner_progress_resumed')

    def test_long_compaction_reports_state_without_claiming_prompt_settlement(self):
        now=[0];events=[]
        p=PromptLifecycle(lambda kind,**fields:events.append((kind,fields)),clock=lambda:now[0])
        p.update({'sessionUpdate':'compaction_update','compactionId':'one','status':'in_progress'})
        now[0]=900;p.update({'sessionUpdate':'compaction_update','compactionId':'one','status':'in_progress'})
        self.assertEqual(p.last_progress,0);self.assertEqual(p.sample()['phase'],'compacting')
        p.update({'sessionUpdate':'compaction_update','compactionId':'one','status':'completed'})
        self.assertEqual(events[-2][1]['prompt_settled'],False)
        self.assertEqual(p.sample()['phase'],'awaiting_agent')

    async def test_prompt_has_no_implicit_whole_turn_timeout_and_keeps_explicit_caller_limit(self):
        c=Client({},lambda *a,**k:None);c.session='same';done=asyncio.Event();calls=[]
        async def request(method,params,update):
            calls.append(method)
            await update({'sessionUpdate':'compaction_update','compactionId':'one','status':'in_progress'})
            await done.wait()
            await update({'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'Done'}})
            return {'stopReason':'end_turn'}
        c.request=request
        task=asyncio.create_task(c.prompt('Existing authorization'))
        await asyncio.sleep(.03);self.assertFalse(task.done())
        done.set();self.assertEqual((await task)['final_text'],'Done');self.assertEqual(calls,['session/prompt'])
        done.clear();cancelled=[]
        async def cancel():cancelled.append(True)
        c.cancel=cancel
        with self.assertRaises(asyncio.TimeoutError):await c.prompt('Explicit bounded probe',timeout=.01)
        self.assertEqual(cancelled,[True])

class WireLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_negotiated_compaction_completion_does_not_settle_prompt(self):
        import tempfile,sys
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            events=[];c=Client({'command':[sys.executable,str(Path(__file__).with_name('lifecycle_fixture.py')),tmp,'normal'],'cwd':tmp},lambda k,**v:events.append((k,v)))
            try:
                await c.start();await c.open_session();pending=asyncio.create_task(c.prompt('Existing work'))
                for _ in range(100):
                    if any(k=='compaction_status' and v['status']=='completed' for k,v in events):break
                    await asyncio.sleep(.005)
                self.assertTrue(any(k=='compaction_status' and v['status']=='completed' for k,v in events))
                self.assertFalse(pending.done())
                Path(tmp,'terminal').touch();self.assertEqual((await pending)['stop_reason'],'end_turn')
            finally:await c.close()

    async def test_transport_closure_during_compaction_is_unknown_not_success_or_replay(self):
        import tempfile,sys,json
        from pathlib import Path
        from acp_client import ProtocolError
        with tempfile.TemporaryDirectory() as tmp:
            c=Client({'command':[sys.executable,str(Path(__file__).with_name('lifecycle_fixture.py')),tmp,'closed'],'cwd':tmp},lambda *a,**k:None)
            try:
                await c.start();await c.open_session()
                with self.assertRaises(ProtocolError):await c.prompt('Existing work')
                methods=[json.loads(line)['method'] for line in Path(tmp,'frames.jsonl').read_text().splitlines()]
                self.assertEqual(methods.count('session/prompt'),1)
            finally:await c.close()
