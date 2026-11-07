import unittest
from sequence_settlement import settle_sequence
class Settlement(unittest.IsolatedAsyncioTestCase):
    async def scenario(self,result,end_at=40,stop_at=None):
        now=0;calls=[];events=[]
        async def request(path,payload=None):
            calls.append((path,payload))
            if path=='/status':return {'action_sequence':{'id':'plan'} if now<end_at else None,'turn_active':stop_at is None or now<stop_at,'busy':now<end_at,'action_lease':{'renewable':True,'lease_id':'lease','task_id':'same'}}
            return {}
        async def sleep(n):
            nonlocal now
            now+=n
        value=await settle_sequence(request,result,lambda *a,**k:events.append((a,k)),sleep=sleep,clock=lambda:now)
        return value,calls,events
    async def test_prompt_completion_waits_actual_domain_settlement_and_renews_only_same_lease(self):
        value,calls,events=await self.scenario({'stop_reason':'end_turn','unsettled_tools':[]})
        self.assertTrue(value['waited']);self.assertEqual([p for path,p in calls if path=='/turn/renew'],[{'lease_id':'lease','task_id':'same'}])
        self.assertFalse(any(path=='/sequence/cancel' for path,_ in calls));self.assertFalse(events[-1][1]['completion_claim'])
    async def test_failed_prompt_or_closed_authority_cancels_and_does_not_renew(self):
        for result,stop in [({'stop_reason':'cancelled'},None),({'stop_reason':'end_turn'},1)]:
            _,calls,_=await self.scenario(result,stop_at=stop)
            self.assertEqual(sum(path=='/sequence/cancel' for path,_ in calls),1);self.assertFalse(any(path=='/turn/renew' for path,_ in calls))
    async def test_unsettled_cancel_is_not_reported_as_completion(self):
        with self.assertRaisesRegex(RuntimeError,'unsettled'):
            await self.scenario({'stop_reason':'cancelled'},end_at=100)
    async def test_no_operation_does_not_create_a_wait_or_prompt(self):
        value,calls,_=await self.scenario({'stop_reason':'end_turn'},end_at=0)
        self.assertEqual(value,{'waited':False});self.assertEqual(len(calls),1)
