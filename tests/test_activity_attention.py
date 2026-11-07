import copy,json,unittest
from harness_capabilities import activity,human_messages
from conversation_attention import ConversationAttention,META,METHOD

class Client:
    session='saved'
    def __init__(self):
        self.calls=[]
        self.info={'_meta':{META:{'version':1,'enabled':True,'method':METHOD,'humanMessages':{'version':1,'budgetPolicy':'independent_of_ambient'},'activity':{'version':1,'contextField':'activities','maxItems':16}}}}
    async def request(self,method,payload):
        self.calls.append((method,payload));return {'action':'engage','id':'event','ticket':'one-use'}

class Activity(unittest.IsolatedAsyncioTestCase):
    def test_strict_negotiation(self):
        c=Client();self.assertTrue(activity(c.info));self.assertTrue(human_messages(c.info))
        for key,value in [('version',True),('version',2),('enabled',False),('method','guessed')]:
            info=copy.deepcopy(c.info);info['_meta'][META][key]=value;self.assertFalse(activity(info));self.assertFalse(human_messages(info))
        for key,value in [('version',True),('version',2),('contextField','messages'),('maxItems',True),('maxItems',0),('maxItems',17)]:
            info=copy.deepcopy(c.info);info['_meta'][META]['activity'][key]=value;self.assertFalse(activity(info))
        self.assertFalse(activity({}));self.assertFalse(activity({'_meta':{META:None}}))

    async def test_activity_keeps_original_source_and_separate_local_delivery(self):
        c=Client();posts=[]
        context={'conversation_id':'room','messages':[],'activities':[{'id':'observed','actor':'human','kind':'movement','summary':'Walked nearby','revision':'original','occurred_at':123}],'trigger_id':'observed'}
        async def request(path,payload=None):
            self.assertEqual(path,'/activity/participation')
            if payload is None:return {'context':context,'signature':'source-bound','occurred_at':123}
            posts.append(payload);return {'queued':True}
        self.assertTrue(await ConversationAttention(lambda *a,**k:None).consider(request,c,activity=True))
        self.assertEqual(c.calls[0][1]['occurredAt'],123);self.assertEqual(c.calls[0][1]['context'],context)
        self.assertEqual(posts,[{'signature':'source-bound','source_id':'observed','action':'engage','offer':{'id':'event','ticket':'one-use'}}])

    async def test_older_or_disabled_host_does_not_receive_unknown_fields_or_fallback_prompt(self):
        for enabled in [False,True]:
            c=Client();c.info['_meta'][META]['enabled']=enabled;del c.info['_meta'][META]['activity']
            async def request(path,payload=None):
                self.assertIsNone(payload)
                return {'signature':'old','context':{'messages':[],'activities':[{'id':'a'}]},'occurred_at':123}
            self.assertFalse(await ConversationAttention(lambda *a,**k:None).consider(request,c,activity=True));self.assertEqual(c.calls,[])

    async def test_mismatched_time_or_oversized_evidence_is_not_sent(self):
        for mismatch in [True,False]:
            c=Client()
            async def request(path,payload=None):
                self.assertIsNone(payload)
                return {'signature':'bad','occurred_at':123,'context':{'messages':[],'activities':[{'id':'a','occurred_at':124 if mismatch else 123,'summary':'x'*(10 if mismatch else 33000)}],'trigger_id':'a'}}
            self.assertFalse(await ConversationAttention(lambda *a,**k:None).consider(request,c,activity=True));self.assertEqual(c.calls,[])
