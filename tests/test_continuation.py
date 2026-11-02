import unittest
from acp_client import turn_disposition
from adapter import capacity_gate


class ContinuationTests(unittest.TestCase):
    def test_turn_limits_do_not_imply_task_failure(self):
        for reason in ['max_tokens','max_turn_requests']:
            self.assertEqual(turn_disposition({'stop_reason':reason,'unsettled_tools':[]}), 'limited')
            self.assertEqual(turn_disposition({'stop_reason':reason,'unsettled_tools':['tool-1']}), 'interrupted')
            self.assertEqual(turn_disposition({'stop_reason':reason},body_busy=True), 'interrupted')
        for reason in ['cancelled','refusal','unknown']:
            self.assertEqual(turn_disposition({'stop_reason':reason}), 'interrupted')
        self.assertEqual(turn_disposition({'stop_reason':'end_turn'}), 'complete')


class CapacityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_preserves_task_and_queued_messages_until_capacity_returns(self):
        calls=[100.0]*30;state={'pending_messages':1,'task':{'status':'running','deadline':4000000,'turns':6}}
        requests=[];events=[];sleeps=[];waiting={}
        async def request(path,payload):requests.append((path,payload))
        async def sleep(seconds):sleeps.append(seconds)
        observe=lambda kind,**data:events.append(kind)
        for now in [3690,3695]:
            self.assertFalse(await capacity_gate(calls,state,request,observe,waiting,now=now,sleep=sleep))
        self.assertEqual(requests,[('/notice',{'kind':'budget'})])
        self.assertEqual(state,{'pending_messages':1,'task':{'status':'running','deadline':4000000,'turns':6}})
        self.assertEqual(sleeps,[10,5]);self.assertEqual(events,['budget_wait'])
        self.assertTrue(await capacity_gate(calls,state,request,observe,waiting,now=3700,sleep=sleep))
        self.assertEqual(calls,[]);self.assertEqual(events,['budget_wait','budget_resumed'])

    async def test_stopped_or_expired_work_is_never_revived_by_capacity_returning(self):
        for status in ['stopped','budget_exhausted','review']:
            state={'pending_messages':0,'task':{'status':status}};requests=[];waiting={};calls=[100.0]*30
            async def request(path,payload):requests.append(path)
            async def sleep(seconds):pass
            self.assertFalse(await capacity_gate(calls,state,request,lambda *a,**k:None,waiting,now=3690,sleep=sleep))
            self.assertTrue(await capacity_gate(calls,state,request,lambda *a,**k:None,waiting,now=3700,sleep=sleep))
            self.assertEqual(state['task']['status'],status);self.assertEqual(requests,[])
