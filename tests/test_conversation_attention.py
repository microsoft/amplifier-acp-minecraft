import tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from conversation_attention import ConversationAttention

class ConversationAttentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_makes_no_decision_or_planner_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate=ConversationAttention(Path(tmp),{},lambda *a,**k:None)
            gate.evaluate=AsyncMock()
            await gate.consider(AsyncMock(return_value=None))
            gate.evaluate.assert_not_called()

    async def test_hold_and_engage_are_applied_only_to_the_evaluated_revision(self):
        for action in ['hold','engage']:
            with tempfile.TemporaryDirectory() as tmp:
                events=[];gate=ConversationAttention(Path(tmp),{},lambda kind,**v:events.append((kind,v)))
                proposal={'signature':'rev','context':{'agent':{'id':'Builder'},'conversation_id':'room','trigger_id':'message'}}
                result={'policy':'conversation-participation-v1','conversation_id':'room','trigger_id':'message','action':action}
                gate.evaluate=AsyncMock(return_value=(result,20))
                request=AsyncMock(side_effect=[proposal,proposal,{'admitted':action=='engage'}])
                with patch('conversation_attention.asyncio.sleep',new=AsyncMock()):await gate.consider(request)
                self.assertEqual(request.call_args.args,('/participation',{'signature':'rev','action':action}))
                self.assertEqual([e[0] for e in events],['participation_decision_attempt','participation_applied'])

    async def test_failure_never_falls_back_to_planner_and_retries_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate=ConversationAttention(Path(tmp),{},lambda *a,**k:None)
            proposal={'signature':'rev','context':{'agent':{'id':'Builder'},'trigger_id':'m'}}
            gate.evaluate=AsyncMock(side_effect=RuntimeError('unavailable'))
            request=AsyncMock(return_value=proposal)
            with patch('conversation_attention.asyncio.sleep',new=AsyncMock()):
                await gate.consider(request);await gate.consider(request)
            self.assertEqual(gate.evaluate.call_count,1)
            self.assertTrue(all(len(c.args)==1 for c in request.call_args_list))
