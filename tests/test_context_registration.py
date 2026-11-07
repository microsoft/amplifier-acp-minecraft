import unittest
from context_registration import registration


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
