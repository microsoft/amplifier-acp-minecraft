import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
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

    async def test_local_preflight_blocks_repeated_evaluation_until_capacity_changes(self):
        client=Client();logs=[];eligible=False;gets=0;posts=[]
        async def request(path,payload=None):
            nonlocal gets
            if payload is None:
                gets+=1
                return {'signature':'same','context':{},'occurred_at':123,
                        'delivery':{'eligible':eligible,'reason_code':'inbox_full' if not eligible else None}}
            posts.append(payload);return {'queued':True}
        a=ConversationAttention(lambda kind,**data:logs.append((kind,data)))
        for _ in range(5):self.assertFalse(await a.consider(request,client))
        self.assertEqual(gets,5);self.assertFalse(client.calls);self.assertFalse(posts)
        self.assertEqual(len(logs),1);self.assertEqual(logs[0][1]['stage'],'local_preflight')
        self.assertFalse(logs[0][1]['evaluation_requested']);self.assertFalse(logs[0][1]['acp_admitted'])
        eligible=True
        self.assertTrue(await a.consider(request,client));self.assertEqual(len(client.calls),1)

    async def test_same_rejected_proposal_backs_off_but_new_source_does_not_wait(self):
        client=Client();logs=[];signature='first';clock=[100.0]
        async def request(path,payload=None):
            if payload is None:return {'signature':signature,'context':{},'occurred_at':123}
            raise HTTPError('http://fixture/participation',409,'Conflict',{},io.BytesIO(
                json.dumps({'code':'source_changed','error':'PRIVATE_BODY_TEXT'}).encode()))
        a=ConversationAttention(lambda kind,**data:logs.append((kind,data)))
        with patch('conversation_attention.time.time',side_effect=lambda:clock[0]):
            self.assertFalse(await a.consider(request,client))
            clock[0]=105;self.assertFalse(await a.consider(request,client))
            self.assertEqual(len(client.calls),1)
            clock[0]=110;self.assertFalse(await a.consider(request,client))
            clock[0]=120;self.assertFalse(await a.consider(request,client))
            self.assertEqual(len(client.calls),2)
            signature='new';self.assertFalse(await a.consider(request,client))
            self.assertEqual(len(client.calls),3)
        self.assertEqual([e[1]['retry_after_seconds'] for e in logs],[10,20,10])
        for _,e in logs:
            self.assertEqual(e['stage'],'local_delivery');self.assertEqual(e['http_status'],409)
            self.assertEqual(e['reason_code'],'source_changed');self.assertTrue(e['evaluation_requested'])
            self.assertFalse(e['acp_admitted'])
        self.assertNotIn('PRIVATE_BODY_TEXT',json.dumps(logs))

    async def test_error_body_is_bounded_and_unknown_text_is_not_logged(self):
        class BoundedBody(io.BytesIO):
            def read(self,size=-1):
                self.requested=size
                return super().read(size)
        body=BoundedBody(json.dumps({'code':'SECRET_CODE','error':'PRIVATE'*10000}).encode())
        logs=[]
        async def request(path,payload=None):
            if payload is None:return {'signature':'s','context':{},'occurred_at':123}
            raise HTTPError('http://fixture/SECRET_URL',503,'SECRET_REASON',{},body)
        self.assertFalse(await ConversationAttention(lambda kind,**data:logs.append(data)).consider(request,Client()))
        self.assertGreater(body.requested,0);self.assertLessEqual(body.requested,2049)
        self.assertEqual(logs[0]['http_status'],503);self.assertEqual(logs[0]['reason_code'],'unknown')
        self.assertNotIn('PRIVATE',json.dumps(logs));self.assertNotIn('SECRET',json.dumps(logs))

    async def test_host_failure_is_distinct_from_local_delivery(self):
        client=Client();logs=[];posts=[]
        async def fail(method,payload):raise RuntimeError('PRIVATE_HOST_ERROR')
        client.request=fail
        async def request(path,payload=None):
            if payload is None:return {'signature':'s','context':{},'occurred_at':123}
            posts.append(payload)
        self.assertFalse(await ConversationAttention(lambda kind,**data:logs.append(data)).consider(request,client))
        self.assertEqual(logs[0]['stage'],'host_evaluation');self.assertIsNone(logs[0]['http_status'])
        self.assertFalse(posts);self.assertNotIn('PRIVATE_HOST_ERROR',json.dumps(logs))

    async def test_repeated_unknown_rejection_backoff_is_capped(self):
        client=Client();logs=[];clock=[100.0]
        async def request(path,payload=None):
            if payload is None:return {'signature':'s','context':{},'occurred_at':123}
            raise RuntimeError('PRIVATE_FAILURE')
        a=ConversationAttention(lambda kind,**data:logs.append(data))
        with patch('conversation_attention.time.time',side_effect=lambda:clock[0]):
            for _ in range(7):
                self.assertFalse(await a.consider(request,client))
                clock[0]=a.retry_after
        self.assertEqual([e['retry_after_seconds'] for e in logs],[10,20,40,80,120,120,120])
        self.assertEqual(len(client.calls),7)
        self.assertTrue(all(e['reason_code']=='unknown' for e in logs))

    async def test_failed_source_fetch_is_logged_and_does_not_poll_or_evaluate_during_backoff(self):
        client=Client();logs=[];fetches=[]
        async def request(path,payload=None):
            fetches.append(path)
            raise HTTPError('http://fixture/private',503,'Unavailable',{},io.BytesIO(b'not JSON'))
        a=ConversationAttention(lambda kind,**data:logs.append(data))
        with patch('conversation_attention.time.time',return_value=100):
            self.assertFalse(await a.consider(request,client))
            self.assertFalse(await a.consider(request,client))
        self.assertEqual(len(fetches),1);self.assertFalse(client.calls)
        self.assertEqual(logs[0]['stage'],'source_fetch');self.assertEqual(logs[0]['http_status'],503)
        self.assertFalse(logs[0]['evaluation_requested'])

    async def test_legacy_body_reason_is_classified_without_logging_raw_text(self):
        logs=[]
        async def request(path,payload=None):
            if payload is None:return {'signature':'s','context':{},'occurred_at':123}
            raise HTTPError('http://fixture/participation',400,'Bad Request',{},io.BytesIO(json.dumps({
                'error':'Peer participation budget or human-activity window expired'}).encode()))
        self.assertFalse(await ConversationAttention(lambda kind,**data:logs.append(data)).consider(request,Client()))
        self.assertEqual(logs[0]['reason_code'],'peer_budget_or_window')
        self.assertEqual(logs[0]['stage'],'local_delivery')

    async def test_recovery_uses_fresh_offer_without_renewing_source_time_or_trigger(self):
        client=Client();posts=[];eligible=True;clock=[100.0]
        async def evaluate(method,payload):
            client.calls.append((method,payload))
            n=len(client.calls)
            return {'action':'engage','id':f'event-{n}','ticket':f'ticket-{n}'}
        client.request=evaluate
        async def request(path,payload=None):
            if payload is None:return {'signature':'same','context':{'trigger_id':'original'},'occurred_at':123,
                'delivery':{'eligible':eligible,'reason_code':'inbox_full' if not eligible else None}}
            posts.append(payload)
            if len(posts)==1:raise HTTPError('http://fixture',429,'Full',{},io.BytesIO(b'{"code":"inbox_full"}'))
            return {'queued':True}
        a=ConversationAttention(lambda *a,**k:None)
        with patch('conversation_attention.time.time',side_effect=lambda:clock[0]):
            self.assertFalse(await a.consider(request,client))
            clock[0]=101;eligible=False
            self.assertFalse(await a.consider(request,client))
            eligible=True
            self.assertTrue(await a.consider(request,client))
        self.assertEqual([p['offer']['ticket'] for p in posts],['ticket-1','ticket-2'])
        self.assertEqual([p['occurredAt'] for _,p in client.calls],[123,123])
        self.assertEqual([p['context']['trigger_id'] for _,p in client.calls],['original','original'])

    async def test_instance_duplicate_hold_is_not_reinterpreted_as_permission_to_retry(self):
        client=Client();posts=[];logs=[]
        async def evaluate(method,payload):
            client.calls.append((method,payload))
            return {'action':'hold','reason':'duplicate','id':'existing-event'}
        client.request=evaluate
        async def request(path,payload=None):
            if payload is None:return {'signature':'same','context':{'trigger_id':'original'},'occurred_at':123}
            posts.append(payload);return {'queued':False}
        a=ConversationAttention(lambda kind,**data:logs.append(data))
        self.assertFalse(await a.consider(request,client))
        self.assertEqual(posts,[{'signature':'same','action':'hold','source_id':'original'}])
        self.assertEqual(logs[0]['reason'],'duplicate')

    async def test_lost_delivery_reply_reconciles_fresh_source_without_replaying_accepted_work(self):
        for enabled in (True,False):
            with self.subTest(host_attention=enabled):
                client=Client(enabled=enabled);logs=[];posts=[];queued=[];pending=['original'];clock=[100.0]
                async def request(path,payload=None):
                    if payload is None:
                        if not pending:return None
                        return {'signature':pending[-1],'context':{'trigger_id':pending[-1]},'occurred_at':123}
                    posts.append(payload);queued.extend(pending);pending.clear()
                    # The body committed, but the HTTP reply disappeared.
                    raise TimeoutError('PRIVATE_REPLY_TIMEOUT')
                a=ConversationAttention(lambda kind,**data:logs.append(data))
                with patch('conversation_attention.time.time',side_effect=lambda:clock[0]):
                    self.assertFalse(await a.consider(request,client))
                    clock[0]=1000
                    for _ in range(3):self.assertFalse(await a.consider(request,client))
                    self.assertEqual(len(posts),1);self.assertEqual(queued,['original'])
                    pending.append('fresh-human-message')
                    self.assertFalse(await a.consider(request,client))
                self.assertEqual(queued,['original','fresh-human-message'])
                self.assertTrue(all(e['delivery_outcome']=='unknown' for e in logs))
                self.assertTrue(all(e['queued'] is None for e in logs))
                self.assertNotIn('PRIVATE_REPLY_TIMEOUT',json.dumps(logs))

    async def test_applied_diagnostics_do_not_echo_host_reason_or_id_payloads(self):
        client=Client();logs=[]
        async def evaluate(method,payload):
            return {'action':'engage','id':'PRIVATE_HOST_ID','ticket':'PRIVATE_TICKET','reason':'PRIVATE_REASON'}
        client.request=evaluate
        async def request(path,payload=None):
            if payload is None:return {'signature':'PRIVATE_SIGNATURE','context':{},'occurred_at':123}
            return {'queued':True}
        self.assertTrue(await ConversationAttention(lambda kind,**data:logs.append(data)).consider(request,client))
        self.assertEqual(logs[0]['reason'],'unknown')
        self.assertNotIn('PRIVATE',json.dumps(logs))

    async def test_malformed_delivery_reply_is_unknown_not_a_queued_receipt(self):
        for reply in (None,{'queued':'PRIVATE_REPLY'},{'queued':False}):
            logs=[]
            async def request(path,payload=None):
                if payload is None:return {'signature':'s','context':{},'occurred_at':123}
                return reply
            a=ConversationAttention(lambda kind,**data:logs.append(data))
            self.assertFalse(await a.consider(request,Client()))
            self.assertEqual(logs[0]['delivery_outcome'],'unknown')
            self.assertEqual(logs[0]['stage'],'local_delivery')
            self.assertNotIn('PRIVATE',json.dumps(logs))

    async def test_expired_offer_is_not_cached_posted_or_given_a_new_trigger(self):
        client=Client();posts=[];logs=[];clock=[100.0]
        async def evaluate(method,payload):
            client.calls.append((method,payload))
            if len(client.calls)==1:return {'action':'engage','id':'expired','ticket':'expired-ticket','expiresAt':99999}
            return {'action':'hold','reason':'duplicate','id':'expired'}
        client.request=evaluate
        async def request(path,payload=None):
            if payload is None:return {'signature':'same','context':{'trigger_id':'original'},'occurred_at':123}
            posts.append(payload);return {'queued':False}
        a=ConversationAttention(lambda kind,**data:logs.append(data))
        with patch('conversation_attention.time.time',side_effect=lambda:clock[0]):
            self.assertFalse(await a.consider(request,client));self.assertFalse(posts)
            clock[0]=110;self.assertFalse(await a.consider(request,client))
        self.assertEqual(posts,[{'signature':'same','action':'hold','source_id':'original'}])
        self.assertEqual(logs[0]['stage'],'offer_validation')
        self.assertEqual([p['occurredAt'] for _,p in client.calls],[123,123])
        self.assertTrue(all(p['context']['trigger_id']=='original' for _,p in client.calls))
