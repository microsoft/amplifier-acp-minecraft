import unittest
from context_registration import registration, readback_matches


class ContextRegistrationTests(unittest.TestCase):
    def cfg(self, identifier='minecraft:jarvis:visit', port=45851):
        return dict(username='Jarvis',world_label='Visit',context_provider_id=identifier,
                    control_port=port,context_token='private',context_grant='private-grant')

    def test_same_player_two_worlds_use_distinct_secrets(self):
        first=registration(self.cfg('minecraft:jarvis:home',45850),[])
        second=registration(self.cfg(),first['providers'])
        self.assertNotEqual(first['secret_ref'],second['secret_ref'])
        self.assertEqual(second['providers'][0],first['provider'])
        self.assertEqual(len(second['providers']),2)

    def test_existing_legacy_registration_keeps_its_secret(self):
        old={'id':'minecraft:jarvis:visit','label':'old','url':'http://127.0.0.1:45851','secret_ref':'minecraft-jarvis-context','configured':True}
        self.assertEqual(registration(self.cfg(),[old])['secret_ref'],'minecraft-jarvis-context')

    def test_new_host_disabled_fields_are_preserved_without_inventing_old_host_fields(self):
        first=registration(self.cfg('minecraft:jarvis:home',45850),[])['provider']
        second=registration(self.cfg(),[])['provider']
        providers=[{**first,'enabled':False},{**second,'enabled':False}]
        result=registration(self.cfg(),providers)
        self.assertEqual([p['enabled'] for p in result['providers']],[False,False])
        self.assertNotIn('enabled',registration(self.cfg(),[first])['provider'])
        self.assertNotIn('enabled',registration(self.cfg(),[first])['providers'][0])

    def test_collision_or_changed_route_refused_before_any_api(self):
        other={'id':'other','url':'http://127.0.0.1:45850','secret_ref':'shared'}
        with self.assertRaisesRegex(ValueError,'Another connection'):
            registration({**self.cfg(),'context_secret_ref':'shared'},[other])
        with self.assertRaisesRegex(ValueError,'elsewhere'):
            registration(self.cfg(),[{**other,'id':'minecraft:jarvis:visit'}])

    def test_missing_staging_and_duplicate_identity_reject(self):
        for key in ('context_token','context_grant','context_provider_id'):
            c=self.cfg();del c[key]
            with self.assertRaises(ValueError):registration(c,[])
        old=registration(self.cfg(),[])['provider']
        with self.assertRaises(ValueError):registration(self.cfg(),[old,old])

    def test_invalid_or_reserved_metadata_refused_before_writes(self):
        for delta in ({'context_provider_id':'bad/id'}, {'context_secret_ref':'control-token'},
                      {'context_secret_ref':'bad.secret'}, {'world_label':'x'*201}):
            with self.assertRaises(ValueError):registration({**self.cfg(),**delta},[])
        with self.assertRaises(ValueError):
            registration(self.cfg(),[{'id':str(i),'url':'http://127.0.0.1:1','secret_ref':'s'+str(i)} for i in range(16)])

    def test_readback_checks_what_was_written_and_ignores_host_reported_fields(self):
        home=registration(self.cfg('minecraft:jarvis:home',45850),[])['provider']
        written=registration(self.cfg(),[{**home,'enabled':False,'configured':True,'effective_enabled':False}])['providers']
        self.assertEqual([p.get('enabled') for p in written],[False,None])
        after=[{**p,'enabled':p.get('enabled',True),'configured':True,'effective_enabled':False} for p in written]
        for same in (after,after[::-1],written):
            self.assertTrue(readback_matches(written,same))
        ours=after[1]
        for different in (after[:1],after+[{**ours,'id':'unexpected'}],[ours,ours],
                          [after[0],{**ours,'url':'http://127.0.0.1:1'}],[after[0],{**ours,'label':'other'}],
                          [after[0],{**ours,'secret_ref':'other'}],[{**after[0],'enabled':True},ours],
                          [{k:v for k,v in after[0].items() if k!='enabled'},ours],
                          [after[0],{k:v for k,v in ours.items() if k!='id'}],[after[0],'not a provider'],None,{}):
            self.assertFalse(readback_matches(written,different),different)

class RegistrationCommandTests(unittest.TestCase):
    def test_no_start_staging_makes_no_instance_or_network_calls_and_keeps_secrets(self):
        import tempfile,json
        from pathlib import Path
        from unittest.mock import patch
        from ops.register_context import main
        with tempfile.TemporaryDirectory() as d:
            h=Path(d);c={'username':'Jarvis','control_port':45851,'context_provider_id':'minecraft:visit'}
            (h/'config.json').write_text(json.dumps(c))
            with patch('ops.register_context.subprocess.run') as process,patch('ops.register_context.urllib.request.urlopen') as http:
                main(['--home',d,'--stage-only'])
                staged=(h/'config.json').read_bytes();main(['--home',d,'--stage-only'])
                self.assertEqual(staged,(h/'config.json').read_bytes())
                process.assert_not_called();http.assert_not_called()
            self.assertFalse((h/'session.json').exists())
            self.assertFalse((h/'workshop.json').exists())

    def test_missing_body_route_cannot_publish_provider_or_secret(self):
        import tempfile,json,urllib.error
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from ops.register_context import main
        with tempfile.TemporaryDirectory() as d:
            h=Path(d);c=ContextRegistrationTests().cfg();(h/'config.json').write_text(json.dumps(c))
            before=(h/'config.json').read_bytes()
            with patch('ops.register_context.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{"providers":[]}')) as process,patch('ops.register_context.urllib.request.urlopen',side_effect=urllib.error.URLError('offline')):
                with self.assertRaises(urllib.error.URLError):main(['--home',d,'--agent-home',d+'/instance'])
                self.assertEqual(process.call_count,1)
                self.assertEqual(process.call_args.args[0][4],'GET')
            self.assertEqual(before,(h/'config.json').read_bytes())
            self.assertFalse((h/'context-registration-receipt.json').exists())

    def test_success_preserves_other_world_and_only_writes_owned_secret(self):
        import tempfile,json,io
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from ops.register_context import main
        old=registration(ContextRegistrationTests().cfg('minecraft:jarvis:home',45850),[])['provider']
        cfg=ContextRegistrationTests().cfg();plan=registration(cfg,[old]);calls=[]
        with tempfile.TemporaryDirectory() as d:
            h=Path(d);(h/'config.json').write_text(json.dumps(cfg))
            def api(command,**kwargs):
                method,path=command[4:6];payload=None
                if '--file' in command:payload=json.loads(Path(command[-1]).read_text())
                calls.append((method,path,payload))
                result={'providers':plan['providers'] if len(calls)==5 else [old]} if method=='GET' else {}
                return SimpleNamespace(returncode=0,stdout=json.dumps(result))
            with patch('ops.register_context.subprocess.run',side_effect=api),patch('ops.register_context.urllib.request.urlopen',return_value=io.BytesIO(b'{"current":{"activity":{"connected":true}}}')):
                main(['--home',d,'--agent-home',d+'/instance'])
            writes=[c for c in calls if c[0]=='PUT']
            self.assertEqual(writes,[('PUT','secrets/'+plan['secret_ref'],{'value':cfg['context_token']}),('PUT','context/providers',{'providers':plan['providers']})])
            self.assertNotEqual(plan['secret_ref'],old['secret_ref'])
            self.assertFalse((h/'session.json').exists())
            receipt=json.loads((h/'context-registration-receipt.json').read_text())
            self.assertFalse(receipt['runtime_namespace_verified'])

    def host(self,d,cfg,providers,stores=True):
        """A host that keeps what is PUT and, like newer Instances, reports more than it was sent."""
        import json,io
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from ops.register_context import main
        h=Path(d);(h/'config.json').write_text(json.dumps(cfg));registry=list(providers)
        def api(command,**kwargs):
            method,path=command[4:6]
            if method=='PUT' and path=='context/providers' and stores:
                registry[:]=[{'enabled':True,**p} for p in json.loads(Path(command[-1]).read_text())['providers']]
            reported=[{**p,'configured':True,'effective_enabled':False} for p in registry]
            return SimpleNamespace(returncode=0,stdout=json.dumps({'providers':reported} if method=='GET' else {}))
        with patch('ops.register_context.subprocess.run',side_effect=api),patch('ops.register_context.urllib.request.urlopen',return_value=io.BytesIO(b'{"current":{"activity":{"connected":true}}}')):
            main(['--home',d,'--agent-home',d+'/instance'])
        return registry

    def test_host_reported_fields_do_not_fail_a_correct_readback(self):
        import tempfile
        from pathlib import Path
        other={**registration(ContextRegistrationTests().cfg('minecraft:jarvis:home',45850),[])['provider'],'enabled':False}
        cfg=ContextRegistrationTests().cfg()
        with tempfile.TemporaryDirectory() as d:
            registry=self.host(d,cfg,[other])
            self.assertEqual(registry,[other,{'enabled':True,**registration(cfg,[])['provider']}])
            self.assertTrue((Path(d)/'context-registration-receipt.json').exists())
            # Registering the same connection again finds its own entry and still reads back cleanly.
            self.assertEqual(self.host(d,cfg,registry),registry)

    def test_unstored_registration_still_fails_readback_without_a_receipt(self):
        import tempfile
        from pathlib import Path
        other={**registration(ContextRegistrationTests().cfg('minecraft:jarvis:home',45850),[])['provider'],'enabled':True}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,'readback differs'):
                self.host(d,ContextRegistrationTests().cfg(),[other],stores=False)
            self.assertFalse((Path(d)/'context-registration-receipt.json').exists())
