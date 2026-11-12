import asyncio
import hashlib
import json
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from installation_session_probe import probe, supervised_endpoint
from installation_participant import LocalInstallation


class SessionProbeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home/'app').mkdir()
        for name in ('acp_client.py','prompt_lifecycle.py'):
            shutil.copy2(Path(__file__).resolve().parent.parent/name,self.home/'app'/name)
        self.log = self.home/'probe.log'
        self.cfg = {'control_port':1234, 'token':'disposable',
                    'context_provider_id':'original-provider','context_grant':'original-grant'}
        self.endpoint = {'command':[sys.executable, str(Path(__file__).with_name('session_probe_fixture.py'))],
                         'cwd':str(self.home), 'env':{'PROBE_LOG':str(self.log)}}
        self.write()

    def write(self):
        (self.home/'config.json').write_text(json.dumps(self.cfg))
        (self.home/'endpoint.json').write_text(json.dumps(self.endpoint))
        bound = {**self.endpoint, 'mcp_servers':[{'type':'http','name':'minecraft',
            'url':'http://127.0.0.1:1234/mcp','headers':[{'name':'Authorization','value':'Bearer disposable'}]}],
            'session_meta':{'io.github.bkrabach.conversation':{'provider_id':'original-provider','grant':'original-grant'}}}
        self.saved = {'session':'original-used-session', 'binding':hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()}
        (self.home/'session.json').write_text(json.dumps(self.saved))

    def events(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_native_transport_only_wraps_exact_original_endpoint(self):
        config=self.home/'driver.json';driver=self.home/'driver'
        profile={'executable':self.endpoint['command'][0],'args':self.endpoint['command'][1:],
                 'cwd':self.endpoint['cwd'],'timeout_seconds':180}
        config.write_text(json.dumps({'version':1,'commands':{'session_endpoint':profile}}))
        original=json.loads(json.dumps(self.endpoint));saved=(self.home/'session.json').read_bytes()
        result=supervised_endpoint(self.endpoint,driver,config)
        self.assertEqual(result['command'],[str(driver),'--config',str(config),'exec','--command','session_endpoint'])
        self.assertEqual(result['env'],original['env']);self.assertEqual(self.endpoint,original)
        self.assertEqual((self.home/'session.json').read_bytes(),saved)
        profile['args']=['different'];config.write_text(json.dumps({'version':1,'commands':{'session_endpoint':profile}}))
        with self.assertRaises(ValueError):supervised_endpoint(self.endpoint,driver,config)
        self.assertEqual(self.events(),[])

    async def test_actual_sdk_loads_original_without_new_prompt_or_saved_file_write(self):
        before = (self.home/'session.json').read_bytes()
        result = await probe(self.home, 3)
        self.assertTrue(result['saved_session_loaded'])
        self.assertEqual(result['session_id'], self.saved['session'])
        self.assertEqual(self.events(), [{'action':'initialize'}, {'action':'load','session':self.saved['session']}])
        self.assertEqual((self.home/'session.json').read_bytes(), before)

    async def test_missing_backend_session_is_not_replaced_or_retried(self):
        self.endpoint['env']['PROBE_MODE']='missing';self.write()
        with self.assertRaises(Exception):await probe(self.home,3)
        self.assertEqual(self.events(), [{'action':'initialize'},{'action':'load','session':self.saved['session']}])
        self.assertEqual(json.loads((self.home/'session.json').read_text()),self.saved)

    async def test_absent_local_session_initializes_only_even_without_load_capability(self):
        self.endpoint['env']['PROBE_MODE']='unsupported';self.write()
        (self.home/'session.json').unlink()
        result=await probe(self.home,3)
        self.assertTrue(result['initialized'])
        self.assertFalse(result['saved_session_present']);self.assertFalse(result['saved_session_loaded'])
        self.assertFalse(result['new_session_created']);self.assertFalse(result['prompt_sent'])
        self.assertEqual(self.events(),[{'action':'initialize'}])
        self.assertFalse((self.home/'session.json').exists())

    async def test_absent_session_failed_initialize_cannot_claim_compatibility(self):
        self.endpoint['env']['PROBE_MODE']='initialize-error';self.write()
        (self.home/'session.json').unlink()
        with self.assertRaises(Exception):await probe(self.home,3)
        self.assertEqual(self.events(),[{'action':'initialize'}])
        self.assertFalse((self.home/'session.json').exists())

    async def test_absent_session_initialize_timeout_is_not_success(self):
        self.endpoint['env']['PROBE_MODE']='initialize-slow';self.write()
        (self.home/'session.json').unlink()
        with self.assertRaises((asyncio.TimeoutError,RuntimeError)):await probe(self.home,1)
        self.assertEqual(self.events(),[{'action':'initialize'}])
        self.assertFalse((self.home/'session.json').exists())

    async def test_participant_runs_initialize_only_in_installed_environment(self):
        (self.home/'session.json').unlink()
        cfg={'home':str(self.home),'state':str(self.home/'owner-state'),
             'venv':sys.prefix,'units':{'body':'acp-minecraft-body-fixture.service',
                                      'controller':'acp-minecraft-agent-fixture.service'}}
        result=await asyncio.to_thread(LocalInstallation(cfg).session,10)
        self.assertTrue(result['initialized']);self.assertFalse(result['saved_session_loaded'])
        self.assertEqual(self.events(),[{'action':'initialize'}])
        self.assertFalse((self.home/'session.json').exists())

    async def test_session_appearing_during_initialize_is_not_accepted(self):
        (self.home/'session.json').unlink()
        home,saved=self.home,self.saved
        class Client:
            def __init__(self,*args,**kwargs):pass
            async def start(self):(home/'session.json').write_text(json.dumps(saved))
            async def close(self):pass
            async def open_session(self,*args):raise AssertionError('No load or create allowed')
        with self.assertRaisesRegex(ValueError,'binding changed'):
            await probe(self.home,3,client_factory=Client)

    async def test_invalid_or_changed_binding_refuses_before_connection(self):
        for saved in (None, [], {'session':'','binding':self.saved['binding']},{**self.saved,'binding':'changed'}):
            (self.home/'session.json').write_text(json.dumps(saved))
            with self.assertRaises(ValueError):await probe(self.home,3)
            self.assertEqual(self.events(),[])

    async def test_no_load_capability_does_not_fallback_to_new(self):
        self.endpoint['env']['PROBE_MODE']='unsupported';self.write()
        with self.assertRaises(Exception):await probe(self.home,3)
        self.assertEqual(self.events(),[{'action':'initialize'}])

    async def test_load_operation_timeout_does_not_prompt_or_replace(self):
        self.endpoint['env']['PROBE_MODE']='slow';self.write()
        with self.assertRaises((asyncio.TimeoutError,RuntimeError)):await probe(self.home,1)
        self.assertEqual(self.events(),[{'action':'initialize'},{'action':'load','session':self.saved['session']}])

    async def test_healthy_replay_can_exceed_inactivity_interval(self):
        self.endpoint['env']['PROBE_MODE']='progressing';self.write()
        result=await probe(self.home,4,idle_timeout=.8)
        self.assertTrue(result['saved_session_loaded'])
        self.assertEqual(self.events(),[{'action':'initialize'},{'action':'load','session':self.saved['session']}])

    async def test_replay_inactivity_still_fails_without_prompt_or_replacement(self):
        self.endpoint['env']['PROBE_MODE']='slow';self.write()
        with self.assertRaises(Exception):await probe(self.home,4,idle_timeout=.8)
        self.assertEqual(self.events(),[{'action':'initialize'},{'action':'load','session':self.saved['session']}])
        self.assertEqual(json.loads((self.home/'session.json').read_text()),self.saved)

    async def test_progress_does_not_extend_absolute_verification_budget(self):
        self.endpoint['env']['PROBE_MODE']='progressing';self.write()
        with self.assertRaises(Exception):await probe(self.home,.8,idle_timeout=.7)
        self.assertEqual(self.events(),[{'action':'initialize'},{'action':'load','session':self.saved['session']}])

    async def test_readonly_budget_is_explicit_and_bounded(self):
        from installation_participant import verification_seconds
        self.assertEqual(verification_seconds({}),12)
        self.assertEqual(verification_seconds({'session_verification_seconds':180}),180)
        for value in (True,0,13,181,None,'180'):
            with self.assertRaises(ValueError):verification_seconds({'session_verification_seconds':value})
        for total,idle in ((181,30),(180,31),(0,0)):
            with self.assertRaises(ValueError):await probe(self.home,total,idle_timeout=idle)
        self.assertEqual(self.events(),[])
