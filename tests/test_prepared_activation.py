"""Candidate contract fixtures; actual new Instance API validation is separate."""
import copy
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import installation_connection_add as add
import test_installation_connection_add as fixtures
from installation_connection import Connection, CONTEXT_MUTATION
from installation_guard import ContinuityError, durable_write, read


class ActivationTests(unittest.TestCase):
    setUp = fixtures.AddTests.setUp
    run_add = fixtures.AddTests.run_add
    assert_untouched = fixtures.AddTests.assert_untouched

    def prepare(self, opt_in=True):
        self.providers[0].update(label='Prepared Workshop',configured=True)
        c=read(self.template)
        if opt_in:c['slots'][0]['activate_context_on_first_connect']=True
        durable_write(self.template,c);self.c=add.load(self.template)
        self.backend.c=self.c;self.request['revision']=self.c['revision']
        result=self.run_add();self.assertEqual(result['state'],'saved')
        self.saved=read(Path(self.cfg['state'])/'saved-connection-config.json')
        self.entry=self.saved['service_connection'];self.connect_id=str(uuid.uuid4())
        self.catalog={'connections':[{**self.entry,'service':'minecraft','enrolled':True,
                       'context_active':False,'state':'busy','request_id':self.connect_id}],
                      'request':{'command':{'connection_id':self.entry['id'],'revision':self.entry['revision'],
                       'request_id':self.connect_id,'action':'connect'}}}
        self.capability=copy.deepcopy(CONTEXT_MUTATION);self.calls=[];self.lose=False
        self.refuse=False;self.other={'id':'unrelated','enabled':False,'label':'Other'}
        self.game.context_api=self.api
        self.game.prepared_context_ready=lambda:self.providers[0]['enabled']
        return result

    def api(self,method,path,payload=None):
        self.calls.append((method,path,copy.deepcopy(payload)))
        if path=='descriptor':return {'context_provider_mutation':self.capability}
        if path=='service-connections':return copy.deepcopy(self.catalog)
        if path=='context/providers':return {'providers':copy.deepcopy(self.providers+[self.other])}
        self.assertEqual(method,'PATCH');self.assertEqual(path,'context/providers/minecraft%3Avisit')
        if self.refuse:raise RuntimeError('candidate fixture HTTP409')
        actual={k:self.providers[0][k] for k in payload['expected_provider']}
        self.assertEqual(actual,payload['expected_provider']);self.assertIs(payload['enabled'],True)
        self.providers[0]['enabled']=True
        if self.lose:raise TimeoutError('ack lost after committed PATCH')
        return {**actual,'enabled':True}

    def op(self,action='status'):
        return Connection(self.saved,{'schema':1,'connection_id':self.entry['id'],
            'revision':self.entry['revision'],'request_id':self.connect_id,'action':action},self.game)

    def patches(self):return [v for v in self.calls if v[0]=='PATCH']

    def settle(self):
        for _ in range(15):
            result=self.op().run()
            if getattr(self.game,'probe_path',None):
                durable_write(self.game.probe_path,{'verified':True,'initialized':True,
                    'saved_session_present':False,'saved_session_loaded':False,
                    'new_session_created':False,'prompt_sent':False})
            if result['settled']:return result
        self.fail('Connect did not settle')

    def test_opt_in_captures_original_disabled_provider_and_template_provenance(self):
        self.prepare();grant=self.saved['prepared_context']['activation']
        self.assertEqual(grant['template_revision'],self.c['revision'])
        self.assertEqual(grant['add_request_id'],self.request['request_id'])
        self.assertFalse(grant['expected_provider']['enabled']);self.assert_untouched()
        self.assertEqual(self.calls,[])

    def test_same_connect_activates_then_loads_unused_session_without_new_prompt(self):
        self.prepare();pending=self.op('connect').run()
        self.assertFalse(pending['settled']);self.assertEqual(self.game.actions,[])
        self.assertEqual(len(self.patches()),1)
        final=self.settle();self.assertEqual(final['state'],'connected');self.assertTrue(final['settled'])
        self.assertEqual(len(self.patches()),1);self.assertFalse(self.other['enabled'])
        self.assertFalse((self.home/'session.json').exists())
        self.assertEqual((self.home/'workshop.json').read_bytes(),self.original['workshop.json'])
        calls=list(self.calls);self.assertEqual(self.op().run(),final);self.assertEqual(calls,self.calls)

    def test_lost_patch_ack_read_only_reconciliation_never_dispatches_twice(self):
        self.prepare();self.lose=True
        with self.assertRaises(TimeoutError):self.op('connect').run()
        self.assertEqual(self.game.actions,[])
        self.assertEqual(self.settle()['state'],'connected');self.assertEqual(len(self.patches()),1)
        receipt=read(Path(self.cfg['state'])/'connections/prepared-context-activation.json')
        self.assertEqual(receipt['phase'],'verified');self.assertTrue(receipt['read_back']['enabled'])

    def test_unknown_or_refused_dispatch_does_not_retry_even_with_new_connect(self):
        self.prepare();self.refuse=True
        with self.assertRaises(RuntimeError):self.op('connect').run()
        self.refuse=False
        for _ in range(3):
            r=self.op().run();self.assertEqual(r['state'],'unknown');self.assertFalse(r['settled'])
        self.assertEqual(len(self.patches()),1);self.assertEqual(self.game.actions,[])
        self.connect_id=str(uuid.uuid4())
        self.catalog['connections'][0]['request_id']=self.connect_id
        self.catalog['request']['command']['request_id']=self.connect_id
        with self.assertRaises(ContinuityError):self.op('connect').run()
        self.assertEqual(len(self.patches()),1)

    def test_crash_before_patch_dispatch_is_unknown_without_automatic_retry(self):
        self.prepare();real=self.game.context_api
        def crash(method,path,payload=None):
            if method=='PATCH':raise OSError('process died before dispatch')
            return real(method,path,payload)
        self.game.context_api=crash
        with self.assertRaises(OSError):self.op('connect').run()
        self.game.context_api=real
        for _ in range(3):self.assertEqual(self.op().run()['state'],'unknown')
        self.assertEqual(self.patches(),[]);self.assertEqual(self.game.actions,[])

    def test_missing_or_wrong_advertisement_does_not_enable_or_start(self):
        self.prepare()
        for cap in (None,{}, {**CONTEXT_MUTATION,'version':2},
                    {**CONTEXT_MUTATION,'version':True},{**CONTEXT_MUTATION,'method':'PUT'}):
            self.capability=cap;r=self.op('connect').run()
            self.assertFalse(r['settled']);self.assertEqual(self.patches(),[])
        self.assertEqual(self.game.actions,[])

    def test_actual_host_gate_request_and_exact_descriptor_required(self):
        self.prepare();original=copy.deepcopy(self.catalog)
        for key,value in [('context_active',True),('revision','changed'),('request_id',str(uuid.uuid4())),
                          ('label','changed'),('context_provider_ids',['other']),('enrolled',False)]:
            self.catalog=copy.deepcopy(original);self.catalog['connections'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ContinuityError):self.op('connect').run()
        self.assertEqual(self.patches(),[]);self.assertEqual(self.game.actions,[])

    def test_changed_provider_or_used_home_cannot_inherit_prepared_grant(self):
        self.prepare();old=copy.deepcopy(self.providers[0])
        for key,value in [('enabled',True),('label','changed'),('url','http://127.0.0.1:9999'),
                          ('secret_ref','other'),('configured',False)]:
            self.providers[0]={**old,key:value}
            with self.subTest(key=key),self.assertRaises(ContinuityError):self.op('connect').run()
        self.providers[0]=old
        durable_write(self.home/'session.json',{'session':'used'})
        with self.assertRaises(ContinuityError):self.op('connect').run()
        self.assertEqual(self.patches(),[]);self.assertEqual(self.game.actions,[])

    def test_later_intentional_disable_never_reactivates_consumed_grant(self):
        self.prepare();self.op('connect').run()
        # Consume via read-back before body start, then simulate an intentional disable.
        self.op().run();self.providers[0]['enabled']=False
        # A fresh Connect after a settled disconnect will pass the same one-use check.
        op=self.op()
        with self.assertRaisesRegex(ContinuityError,'never re-enable'):
            op.prepare_context(None)
        self.assertEqual(len(self.patches()),1)

    def test_no_template_grant_preserves_manual_or_intentional_disabled_state(self):
        self.prepare(opt_in=False)
        self.assertNotIn('activation',self.saved['prepared_context'])
        r=self.op('connect').run();self.assertFalse(r['settled'])
        self.assertIn('No automatic activation',r['message'])
        self.assertEqual(self.calls,[]);self.assertEqual(self.game.actions,[])

    def test_nonboolean_owner_opt_in_rejected(self):
        c=read(self.template);c['slots'][0]['activate_context_on_first_connect']='true'
        durable_write(self.template,c)
        with self.assertRaises(ValueError):add.load(self.template)

    def test_patch_uses_fixed_cli_and_private_payload_not_browser_arguments(self):
        import json
        from types import SimpleNamespace
        from installation_connection import Backend
        self.prepare();b=Backend(self.saved);grant=self.saved['prepared_context']['activation']
        payload={'expected_provider':grant['expected_provider'],'enabled':True}
        with patch('installation_connection.subprocess.run',return_value=SimpleNamespace(stdout='{}')) as run:
            b.context_api('PATCH','context/providers/minecraft%3Avisit',payload)
        argv=run.call_args.args[0]
        self.assertEqual(argv[:6],[str(Path(self.saved['prepared_context']['agent_home'])/'bin/agent-instance'),
            '--home',self.saved['prepared_context']['agent_home'],'api','PATCH','context/providers/minecraft%3Avisit'])
        self.assertEqual(argv[-2],'--file');self.assertEqual(json.loads(Path(argv[-1]).read_text()),payload)
        self.assertEqual(Path(argv[-1]).stat().st_mode & 0o777,0o600)
        self.assertFalse(Path(argv[-1]).is_relative_to(self.home));self.assertEqual(self.game.actions,[])
