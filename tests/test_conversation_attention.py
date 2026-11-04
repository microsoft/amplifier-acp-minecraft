import unittest
from conversation_attention import ConversationAttention,META,METHOD

class Client:
    session='session'
    def __init__(self,action='engage',enabled=True):
        self.info={'_meta':{META:{'version':1,'enabled':enabled,'method':METHOD}}};self.action=action;self.calls=[]
    async def request(self,method,payload):
        self.calls.append((method,payload));return {'action':self.action,'id':'event','ticket':'ticket'}

class Delivery(unittest.IsolatedAsyncioTestCase):
    async def test_host_offer_is_not_reported_as_an_queued_acp_turn(self):
        for action in ('engage','hold'):
            client=Client(action);posts=[];logs=[]
            async def request(path,payload=None):
                if payload is None:return {'signature':'snapshot','context':{'conversation_id':'world'},'occurred_at':123}
                posts.append(payload);return {'queued':payload['action']=='engage'}
            a=ConversationAttention(lambda kind,**data:logs.append((kind,data)))
            result=await a.consider(request,client)
            self.assertEqual(result,action=='engage');self.assertEqual(client.calls[0][0],METHOD)
            self.assertEqual(client.calls[0][1]['occurredAt'],123)
            self.assertFalse(logs[0][1]['acp_admitted'])
            self.assertEqual('offer' in posts[0],action=='engage')
    async def test_source_change_discards_offer_without_prompt(self):
        client=Client();logs=[]
        async def request(path,payload=None):
            if payload is None:return {'signature':'old','context':{},'occurred_at':123}
            raise RuntimeError('source changed')
        a=ConversationAttention(lambda kind,**data:logs.append(kind))
        self.assertFalse(await a.consider(request,client));self.assertEqual(logs,['participation_delivery_error'])
        self.assertFalse(await a.consider(request,client));self.assertEqual(len(client.calls),1)
    async def test_plain_acp_fallback_has_no_provider_dependency(self):
        client=Client(enabled=False);posts=[]
        async def request(path,payload=None):
            if payload is None:return {'signature':'s','context':{},'occurred_at':123}
            posts.append(payload);return {'queued':True}
        self.assertTrue(await ConversationAttention(lambda *a,**k:None).consider(request,client))
        self.assertFalse(client.calls);self.assertNotIn('offer',posts[0])
