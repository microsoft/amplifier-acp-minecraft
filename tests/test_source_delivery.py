import json
import tempfile
import unittest
from harness_capabilities import INSTANCE,SOURCE_META,SOURCE_METHOD,source_delivery,attention_context
from conversation_awareness import Awareness
from acp_client import Client

CAP={'version':1,'metadata':SOURCE_META,'receiptsMethod':SOURCE_METHOD}
def info(cap=CAP):return {'_meta':{INSTANCE:{'inputContinuity':{'sourceDelivery':cap}}}}
SOURCE={'id':'new','revision':'original-revision','occurredAt':123456}
def snapshot():return {'turn_active':True,'revision':'new','messages':[{'id':'old'},{'id':'new','text':'Delivered','source_fact':SOURCE}]}

class SourceDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_changed_source_revision_is_new_evidence_not_replay_of_unknown_input(self):
        c=Client({},lambda *a,**k:None);c.info=info();c.session='s';c.active_prompt_id=7;c.supports_awareness=lambda:True
        calls=[]
        async def request(method,params):
            calls.append(params);raise ConnectionError('lost reply')
        c.request=request
        with tempfile.TemporaryDirectory() as tmp:
            a=Awareness(tmp,c,{'revision':'old'},c.observe)
            await a.consider(snapshot());await a.consider(snapshot());self.assertEqual(len(calls),1)
            changed=snapshot();changed['messages'][-1]['source_fact']={**SOURCE,'revision':'corrected'}
            await a.consider(changed);self.assertEqual(len(calls),2)
            self.assertNotEqual(calls[0]['_meta']['steering']['inputId'],calls[1]['_meta']['steering']['inputId'])
            self.assertEqual(calls[1]['_meta'][SOURCE_META]['sources'][0]['occurredAt'],123456)
            a.sent[0]['state']='incorporated'
            self.assertIsNone(a.final_revision({**changed,'exposed_revision':'new'}),
                              'Old incorporation/cursor must not certify corrected source text')

    def test_attention_only_uses_advertised_schema_and_original_timestamp(self):
        context={'messages':[{'id':'new','sender':'Peer','text':'Delivered'}]}
        for value in (None,{},info({}),info({**CAP,'version':2}),info({**CAP,'version':True}),info({**CAP,'receiptsMethod':'invented'})):
            self.assertFalse(source_delivery(value));self.assertIs(attention_context(context,[SOURCE],value),context)
        enriched=attention_context(context,[SOURCE],info())
        self.assertEqual(enriched['messages'][0]['revision'],SOURCE['revision'])
        self.assertEqual(enriched['messages'][0]['occurred_at'],123456)
        self.assertNotIn('revision',context['messages'][0])
        self.assertNotIn('occurred_at',attention_context(context,[{**SOURCE,'occurredAt':None}],info())['messages'][0])

    async def test_source_metadata_and_receipts_do_not_claim_completion_or_change_freshness(self):
        calls=[];observed=[]
        c=Client({},lambda k,**v:observed.append((k,v)))
        c.info=info();c.session='s';c.active_prompt_id=7;c.supports_awareness=lambda:True
        async def request(method,params):
            calls.append((method,params))
            if method=='_session/steering':return {'outcome':'injected'}
            self.assertEqual(method,SOURCE_METHOD)
            return {'version':1,'receipts':[{'sourceId':'new','revision':SOURCE['revision'],'occurredAt':123456,
                'inputId':a.sent[0]['input_id'],'state':'incorporated','incorporated':True,'completion':'not_established'}]}
        c.request=request
        with tempfile.TemporaryDirectory() as tmp:
            a=Awareness(tmp,c,{'revision':'old'},c.observe)
            await a.consider(snapshot());await a.finish()
            self.assertEqual(calls[0][1]['_meta'][SOURCE_META],{'version':1,'sources':[SOURCE]})
            self.assertEqual(calls[0][1]['_meta']['steering']['activePromptId'],7)
            self.assertEqual(calls[1][1],{'sessionId':'s','sources':[SOURCE]})
            self.assertEqual(a.sent[0]['state'],'received')
            self.assertTrue(a.sent[0]['source_delivery'][0]['incorporated'])
            self.assertIsNone(a.final_revision(snapshot()),'Keep existing final-answer cutoff unchanged')
            again=Awareness(tmp,c,{'revision':'old'},c.observe);await again.consider(snapshot())
            self.assertEqual(len(calls),2,'Never replay possibly accepted updates')
            self.assertNotIn('completed',json.dumps(a.sent))

    async def test_lost_response_remains_unknown_and_mismatched_source_receipt_is_not_evidence(self):
        c=Client({},lambda *a,**k:None);c.info=info();c.session='s';c.active_prompt_id=7;c.supports_awareness=lambda:True
        calls=[]
        async def request(method,params):
            calls.append(method)
            if method=='_session/steering':raise ConnectionError('lost')
            return {'version':1,'receipts':[{'sourceId':'new','revision':'different','occurredAt':123456,
                'inputId':a.sent[0]['input_id'],'state':'incorporated','incorporated':True}]}
        c.request=request
        with tempfile.TemporaryDirectory() as tmp:
            a=Awareness(tmp,c,{'revision':'old'},c.observe);await a.consider(snapshot());await a.finish()
            self.assertEqual(a.sent[0]['state'],'unknown');self.assertFalse(a.sent[0]['source_delivery'][0]['incorporated'])
            self.assertEqual(a.sent[0]['source_delivery'][0]['state'],'unknown')
            other=Awareness(tmp,c,{'revision':'old'},c.observe);await other.consider(snapshot())
            self.assertEqual(calls,['_session/steering',SOURCE_METHOD])
