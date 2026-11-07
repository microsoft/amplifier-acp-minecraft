import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock
from assessment import Assessment, POLICY, context, signature


def state(status='running'):
    return {'username':'test', 'inventory':[], 'events':[], 'public_chat':[],
            'task':{'id':'one','status':status,'goal':'Create an enjoyable place',
                    'deadline':int(time.time()*1000)+60000,'turns':1,'max_turns':10,
                    'wait_for':'A teammate delivers the material' if status=='waiting' else None}}


def result():
    return {'answers':[{'name':'attention','choice':'ready','probabilities':{'ready':.9}},
                       {'name':'reflection','choice':'continue'},
                       {'name':'coordination','choice':'none'}]}


class AssessmentTests(unittest.IsolatedAsyncioTestCase):
    def test_sources_failures_and_privacy(self):
        s=state(); sig=signature(s)
        s['events']=[{'id':'failed-1','kind':'action_failed','action':'move','error':'No path'}]
        self.assertNotEqual(sig,signature(s))
        s['public_chat']=[{'message':'PRIVATE','whisper':True},{'message':'Visible','username':'peer'}]
        c=context(s)
        self.assertNotIn('PRIVATE',json.dumps(c))
        self.assertIn('tool execution receipt',json.dumps(c))
        self.assertIn('not verified fact',json.dumps(c))
        s['time']=123; first=signature(s); s['time']=456
        self.assertEqual(first,signature(s))
        s['task']['started_at']='2026-11-02T15:00:00Z'
        self.assertNotIn('failed-1',json.dumps(context(s)))

    async def test_shadow_records_without_waking_or_advising(self):
        with tempfile.TemporaryDirectory() as d:
            a=Assessment(Path(d),{'mode':'shadow'},lambda *a,**k:None)
            a.evaluate=AsyncMock(return_value=(result(),70))
            self.assertFalse(await a.consider(state('waiting')))
            self.assertTrue((Path(d)/'assessments.jsonl').exists())
            self.assertIsNone(await a.before_turn(state()))

    def test_waiting_uses_new_evidence_not_old_construction_history(self):
        s=state('waiting');s['task']['wait_started_at']='2026-11-02T15:00:00Z'
        s['task']['progress']=[{'summary':'Old long construction report'}]
        s['events']=[{'id':'old','time':'2026-11-02T14:59:00Z','kind':'action_failed','error':'old error'}]
        s['public_chat']=[{'kind':'chat','message':'Old','time':'2026-11-02T14:59:00Z'},
                          {'kind':'chat','message':'New result','time':'2026-11-02T15:01:00Z'},
                          {'kind':'chat','message':'PRIVATE','whisper':True,'time':'2026-11-02T15:02:00Z'}]
        c=context(s);self.assertEqual(c['working_summary'],'')
        self.assertIn('New result',json.dumps(c));self.assertNotIn('old error',json.dumps(c))
        self.assertNotIn('PRIVATE',json.dumps(c));self.assertNotIn('Old',json.dumps(c))

    async def test_authority_states_dedup_budget_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            a=Assessment(Path(d),{'mode':'advisory','interval_seconds':0,'max_calls_per_hour':2},lambda *a,**k:None)
            a.evaluate=AsyncMock(return_value=(result(),70))
            for status in ('stopped','blocked','review','needs_review','budget_exhausted'):
                self.assertFalse(await a.consider(state(status)))
                self.assertIsNone(await a.before_turn(state(status)))
            a.evaluate.assert_not_called()
            s=state('waiting'); self.assertTrue(await a.consider(s))
            self.assertFalse(await a.consider(s))
            advisory=await a.before_turn(state()); self.assertEqual(advisory['policy'],POLICY)
            s['inventory']=[{'name':'log','count':4}]
            self.assertFalse(await a.consider(s))
            self.assertEqual(a.evaluate.call_count,2)
        with tempfile.TemporaryDirectory() as d:
            a=Assessment(Path(d),{'mode':'advisory'},lambda *a,**k:None)
            a.evaluate=AsyncMock(side_effect=RuntimeError('service unavailable'))
            self.assertFalse(await a.consider(state('waiting')))
