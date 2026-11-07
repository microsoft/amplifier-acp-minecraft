import asyncio
import hashlib
import json
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from installation_session_probe import probe


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

    async def test_absent_local_session_does_not_create_or_initialize(self):
        (self.home/'session.json').unlink()
        result=await probe(self.home,3)
        self.assertFalse(result['saved_session_present']);self.assertFalse(result['new_session_created'])
        self.assertEqual(self.events(),[])

    async def test_invalid_or_changed_binding_refuses_before_connection(self):
        for saved in ({'session':'','binding':self.saved['binding']},{**self.saved,'binding':'changed'}):
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
