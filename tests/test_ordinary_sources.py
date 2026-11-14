"""Actual SDK wire plus retained adapter delivery state; no provider/world."""
import asyncio
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import adapter
from acp_client import Client, ProtocolError
from conversation_awareness import Awareness
from harness_capabilities import ordinary_sources
SOURCE={'id':'original-human-input','revision':'original-revision','occurredAt':1794670000123}
SNAPSHOT={'revision':SOURCE['id'],'messages':[{'id':SOURCE['id'],'source_fact':SOURCE}]}
MESSAGES=[{'id':SOURCE['id'],'source':'human','message':'Original request'}]
class OrdinarySources(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.state=self.home/'fixture.json'
        self.events=[];self.clients=[];self.client=await self.connect()
    async def connect(self,mode='supported',load=False):
        c=Client({'command':[sys.executable,str(Path(__file__).with_name('ordinary_source_fixture.py')),str(self.state),mode],'cwd':str(self.home)},lambda kind,**value:self.events.append((kind,value)))
        self.clients.append(c);await c.start();await c.open_session('original-session' if load else None);return c
    async def asyncTearDown(self):
        for c in self.clients:await c.close()
        self.tmp.cleanup()
    def awareness(self,client=None,snapshot=SNAPSHOT):return Awareness(self.home,client or self.client,snapshot,lambda *a,**k:None,binding='original-binding')
    def recorded(self):return json.loads(self.state.read_text())
    async def send(self,a,text='normal',messages=MESSAGES,attention=None):
        meta=await a.ordinary_prompt(messages)
        result=await a.client.prompt(text,timeout=3,source_metadata=meta,attention_offer=attention)
        await a.finish();return meta,result
    async def test_original_metadata_and_attention_share_actual_sdk_prompt(self):
        a=self.awareness();meta,result=await self.send(a,attention={'id':'offer','ticket':'private-fixture'})
        self.assertEqual(meta['sources'],[SOURCE]);self.assertEqual(result['stop_reason'],'end_turn')
        row=self.recorded()['prompts'][0];self.assertEqual(row['metadata'],meta);self.assertEqual(row['attention'],{'id':'offer','ticket':'private-fixture'})
        self.assertEqual(self.recorded()['queries'][0],{'sessionId':'original-session','sources':[SOURCE]})
        fact=a.ordinary[0]['source_delivery'][0];self.assertEqual(fact['state'],'submitted');self.assertFalse(fact['incorporated']);self.assertEqual(fact['completion'],'not_established')
        self.assertEqual([x['state'] for x in fact['instance_work']['references']],['proposed','accepted'])
        self.assertFalse((self.home/'workshop.json').exists());self.assertNotIn('private-fixture',json.dumps(self.events))
    async def test_lost_reply_restart_inspects_once_without_second_prompt(self):
        a=self.awareness();meta=await a.ordinary_prompt(MESSAGES)
        with self.assertRaises((ProtocolError,ConnectionError,EOFError,RuntimeError)):await self.client.prompt('lost',timeout=3,source_metadata=meta)
        await self.client.close();c=await self.connect(load=True);restored=self.awareness(c);self.assertEqual(restored.receipts[0]['state'],'unknown')
        with self.assertRaisesRegex(RuntimeError,'inspect.*do not replay'):await restored.ordinary_prompt(MESSAGES)
        self.assertEqual(len(self.recorded()['prompts']),1);self.assertEqual(restored.receipts[0]['source_delivery'][0]['state'],'submitted')
        self.assertEqual(self.recorded()['rows'][meta['inputId']]['original_actor'],'original-human')
    async def test_retained_input_cannot_escape_via_lost_facts_or_capability_downgrade(self):
        await self.send(self.awareness())
        for mode,snapshot in [('legacy',SNAPSHOT),('supported',{'revision':'later','messages':[]})]:
            c=await self.connect(mode,load=True);a=self.awareness(c,snapshot)
            with self.assertRaisesRegex(RuntimeError,'inspect.*replay'):await a.ordinary_prompt(MESSAGES)
        self.assertEqual(len(self.recorded()['prompts']),1)
    async def test_plain_acp_for_legacy_and_missing_original_source(self):
        for mode in ('legacy','steering-only'):
            c=await self.connect(mode);a=self.awareness(c);meta,_=await self.send(a);self.assertIsNone(meta)
        for messages,snapshot in [([{'source':'continuation'}],SNAPSHOT),([{'id':'private-source','source':'human'}],SNAPSHOT),(MESSAGES+[{'id':'missing'}],SNAPSHOT),(MESSAGES,{'revision':'old','messages':[]})]:
            a=self.awareness(snapshot=snapshot);meta,_=await self.send(a,messages=messages);self.assertIsNone(meta)
        self.assertTrue(all(p['metadata'] is None for p in self.recorded()['prompts']));self.assertEqual(self.awareness().receipts,[])
    async def test_changed_revision_retains_original_time_and_new_identity(self):
        first,_=await self.send(self.awareness());changed={**SOURCE,'revision':'corrected'}
        a=self.awareness(snapshot={'revision':SOURCE['id'],'messages':[{'id':SOURCE['id'],'source_fact':changed}]});second,_=await self.send(a)
        self.assertNotEqual(first['inputId'],second['inputId']);self.assertEqual(second['sources'],[changed]);self.assertEqual(len(self.recorded()['prompts']),2)
    async def test_receipt_correlation_and_separate_work_coverage(self):
        for mode in ('wrong-source','wrong-input','evicted-delivery','partial','bad-work','zero-work'):
            source={**SOURCE,'id':mode};messages=[{'id':mode,'source_fact':source}];c=await self.connect(mode);a=self.awareness(c);await self.send(a,messages=messages);fact=a.ordinary[0]['source_delivery'][0]
            if mode in ('wrong-source','wrong-input','evicted-delivery'):self.assertEqual(fact['state'],'unknown');self.assertFalse(fact['incorporated'])
            if mode in ('wrong-source','bad-work'):self.assertEqual(fact['instance_work'],{'references':[],'coverage':'unknown'})
            elif mode=='zero-work':self.assertEqual(fact['instance_work'],{'references':[],'coverage':'retained_session_records'})
            else:self.assertEqual(len(fact['instance_work']['references']),2);self.assertEqual(fact['instance_work']['coverage'],'partial' if mode=='partial' else 'retained_session_records')
            self.assertEqual(fact['completion'],'not_established')
    async def test_explicit_steering_refusal_promotes_same_input_and_keeps_original_actor(self):
        for state in ('notAccepted','promptRequired'):
            source={**SOURCE,'id':state};key='original-steering-'+state
            await self.client.request('_test/seed',{'id':key,'row':{'kind':'steering','sources':[source],'state':state,'incorporated':False,'original_actor':'original-author-before-group-handoff'}})
            a=self.awareness();a.receipts.append({'input_id':key,'session_id':self.client.session,'binding':'original-binding','sources':[source],'source_ids':[source['id']],'state':'unknown'});a._save()
            meta,_=await self.send(a,messages=[{'id':source['id'],'source_fact':source}]);self.assertEqual(meta['inputId'],key)
            self.assertEqual(self.recorded()['rows'][key]['original_actor'],'original-author-before-group-handoff')
            with self.assertRaisesRegex(RuntimeError,'inspect.*replay'):await self.awareness().ordinary_prompt([{'id':source['id'],'source_fact':source}])
        self.assertEqual(len(self.recorded()['prompts']),2)
    async def test_unknown_or_incorporated_steering_never_promotes(self):
        for state,incorporated in [('unknown',False),('submitted',False),('notAccepted',True)]:
            key=state+str(incorporated);source={**SOURCE,'id':key}
            await self.client.request('_test/seed',{'id':key,'row':{'kind':'steering','sources':[source],'state':state,'incorporated':incorporated}})
            a=self.awareness();a.receipts.append({'input_id':key,'session_id':self.client.session,'binding':'original-binding','sources':[source],'source_ids':[key],'state':'unknown'});a._save()
            with self.assertRaisesRegex(RuntimeError,'inspect.*replay'):await a.ordinary_prompt([{'id':key,'source_fact':source}])
        self.assertEqual(self.recorded()['prompts'],[])
    async def test_invalid_negotiation_and_unavailable_journal_never_send_metadata(self):
        original=self.client.info['_meta']['io.github.bkrabach.agent-instance']['inputContinuity']['sourceDelivery']
        for change in ({'ordinaryPrompts':1},{'promptRetry':'retry'},{'version':True}):
            self.client.info['_meta']['io.github.bkrabach.agent-instance']['inputContinuity']['sourceDelivery']={**original,**change};self.assertFalse(ordinary_sources(self.client.info))
            with self.assertRaises(ValueError):await self.client.prompt('normal',source_metadata={'version':1,'inputId':'x','sources':[SOURCE]})
        self.client.info['_meta']['io.github.bkrabach.agent-instance']['inputContinuity']['sourceDelivery']=original
        (self.home/'awareness-receipts.json').write_text('invalid')
        with self.assertRaisesRegex(RuntimeError,'Cannot retain'):await self.awareness().ordinary_prompt(MESSAGES)
        self.assertFalse(self.state.exists())
    async def test_stale_refusal_missing_incorporation_and_changed_binding_do_not_promote(self):
        for mode in ('query-fails','missing-incorporation','changed-binding','legacy-binding'):
            c=await self.connect(mode,load=True);a=self.awareness(c);key=mode
            source={**SOURCE,'id':mode}
            await c.request('_test/seed',{'id':key,'row':{'kind':'steering','sources':[source],'state':'notAccepted','incorporated':False}})
            receipt={'input_id':key,'session_id':c.session,'binding':'original-binding','sources':[source],'source_ids':[key],'state':'unknown',
                     'source_receipt_current':True,'source_delivery':[{**source,'state':'notAccepted','incorporated':False,'evidence_origin':'host_source_receipt'}]}
            if mode=='changed-binding':receipt['binding']='different-endpoint-or-grant'
            if mode=='legacy-binding':receipt.pop('binding')
            a.receipts.append(receipt);a._save()
            with self.assertRaisesRegex(RuntimeError,'inspect.*replay'):await a.ordinary_prompt([{'id':key,'source_fact':source}])
        self.assertEqual(self.recorded()['prompts'],[])

    async def test_legacy_uncertain_source_id_without_revision_does_not_become_fresh(self):
        a=self.awareness()
        a.receipts.append({'input_id':'legacy-steering','session_id':self.client.session,
                           'source_ids':[SOURCE['id']],'state':'unknown'})
        a._save()
        with self.assertRaisesRegex(RuntimeError,'inspect.*replay'):
            await a.ordinary_prompt(MESSAGES)
        self.assertFalse(self.state.exists())
        # A retained but never dispatched history row is not a delivery record.
        a.receipts[0].update(state='history_only',reason='unsupported');a._save()
        meta,_=await self.send(a)
        self.assertEqual(meta['sources'],[SOURCE]);self.assertEqual(len(self.recorded()['prompts']),1)

    async def test_batch_order_and_overlap_do_not_create_another_send(self):
        other={**SOURCE,'id':'second'}
        messages=[{'id':f['id'],'source_fact':f} for f in [SOURCE,other]]
        await self.send(self.awareness(),messages=messages)
        for selected in (list(reversed(messages)),messages[:1],messages+[{'id':'third','source_fact':{**SOURCE,'id':'third'}}]):
            with self.assertRaisesRegex(RuntimeError,'inspect.*replay'):await self.awareness().ordinary_prompt(selected)
        self.assertEqual(len(self.recorded()['prompts']),1)

    async def test_actual_controller_routes_original_sources_and_preserves_task(self):
        active=False;paths=[]
        task={'id':'domain-owned','status':'blocked','turns':23,'max_turns':45,'deadline':9999999999999}
        original_task=json.dumps(task,sort_keys=True)
        world={'ready':True,'busy':False,'generation':1,'task':task,'conversation_only':True,'conversation':SNAPSHOT}
        def control(cfg,path,payload=None):
            nonlocal active
            paths.append((path,payload))
            if path in ('/state','/observation','/status'):return {**world,'turn_active':active,'pending_messages':1,'action_lease':{'version':1,'renewable':False}}
            if path=='/conversation/admission':return {'version':1,'unmetered':True,'eligible_ids':[SOURCE['id']]}
            if path=='/inbox/peek':return MESSAGES
            if path=='/turn':active=True;return {}
            if path=='/conversation':return SNAPSHOT
            if path=='/operator-inputs':return {'revision':'empty','messages':[]}
            if path=='/finish':raise asyncio.CancelledError()
            if path in ('/recover','/inbox/retire-expired'):return {}
            raise AssertionError(path)
        cfg={'control_port':1,'token':'fixture','incoming_chat_only':True}
        endpoint={'command':[sys.executable,str(Path(__file__).with_name('ordinary_source_fixture.py')),str(self.state),'supported'],'cwd':str(self.home)}
        bound={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1/mcp','headers':[{'name':'Authorization','value':'Bearer fixture'}]}]}
        binding=hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()
        session={'binding':binding,'session':'original-session'}
        for name,value in [('config',cfg),('endpoint',endpoint),('session',session)]:
            (self.home/(name+'.json')).write_text(json.dumps(value))
        output=io.StringIO()
        with patch.object(adapter,'control',control),contextlib.redirect_stdout(output):
            with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(adapter.run(self.home),10)
        record=self.recorded();self.assertEqual(len(record['prompts']),1)
        self.assertEqual(record['prompts'][0]['metadata']['sources'],[SOURCE])
        self.assertEqual(json.loads((self.home/'session.json').read_text()),session)
        self.assertEqual(json.dumps(task,sort_keys=True),original_task)
        self.assertEqual([v for p,v in paths if p=='/finish'],[{'error':False,'budget_limited':False}])
        self.assertFalse(any(p in ('/task','/wake','/action','/turn/renew') for p,_ in paths))
        receipt=json.loads((self.home/'awareness-receipts.json').read_text())[0]
        self.assertEqual(receipt['binding'],binding);self.assertEqual(receipt['source_delivery'][0]['completion'],'not_established')
        self.assertFalse(any(json.loads(line)['kind']=='adapter_error' for line in output.getvalue().splitlines()))

if __name__=='__main__':unittest.main()
