import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from installation_connection import Connection, descriptor
from installation_guard import ContinuityError, NotIdle, durable_write, read
from installation_participant import Participant
from test_installation_participant import FakeInstallation


class Fake(FakeInstallation):
    def connected(self):return self.body['ready']
    def start_probe(self,path):
        self.actions.append(('session','start-original-only'))
        self.probe_path=path
        return {'pid':123,'start_ticks':'1','boot_id':'boot'}
    def probe_alive(self,identity):return True
    def settle_probe(self,success=True):
        durable_write(self.probe_path,{'verified':success,'initialized':success,
            'saved_session_present':True,'saved_session_loaded':success,
            'new_session_created':False,'prompt_sent':False})


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'game';self.home.mkdir()
        self.backend=Fake(self.home)
        self.cfg={'home':str(self.home),'state':str(self.root/'owner'),
            'service_connection':{'id':'minecraft-visit','label':'Visit',
                'revision':'a'*64,'context_provider_ids':['minecraft:tester:visit']}}
        self.id=str(uuid.uuid4())
    def op(self,action='status',identifier='current'):
        return Connection(self.cfg,{'schema':1,'connection_id':'minecraft-visit',
            'revision':'a'*64,'action':action,'request_id':self.id if identifier=='current' else identifier},self.backend)
    def ack(self):
        durable_write(self.home/'installation-updates/controller-idle.json',
            {'transaction_id':self.id,**self.backend.units['controller']['process_identity']})
    def disconnect(self):
        self.assertFalse(self.op('disconnect').run()['settled']);self.ack()
        for _ in range(8):
            result=self.op().run()
            if result['settled']:return result
        self.fail('disconnect never settled')
    def connect_ready(self):
        self.id=str(uuid.uuid4());self.op('connect').run()
        for _ in range(8):
            result=self.op().run()
            if result.get('context_ready'):return result
        self.fail('context never ready')
    def connect_settle(self):
        self.connect_ready();self.op().run();self.backend.settle_probe()
        for _ in range(5):
            result=self.op().run()
            if result['settled']:return result
        self.fail('connect never settled')
    def test_disconnect_waits_for_ack_and_busy_effects_then_stops_once(self):
        before=(self.home/'workshop.json').read_bytes()
        self.op('disconnect').run();self.ack();self.backend.body['busy']=True
        with self.assertRaises(NotIdle):self.op().run()
        self.assertEqual(self.backend.actions,[])
        self.backend.body['busy']=False
        for _ in range(5):r=self.op().run()
        self.assertEqual(r['state'],'disconnected');self.assertTrue(r['settled'])
        self.assertEqual(self.backend.actions,[('controller','stop'),('body','stop')])
        self.assertEqual(before,(self.home/'workshop.json').read_bytes())
        self.assertTrue((self.home/'installation-updates/gate.json').exists())
        self.assertEqual(read(self.home/'installation-connections/state.json')['phase'],'disconnected')
    def test_context_readiness_precedes_probe_and_release(self):
        self.disconnect();before=(self.home/'workshop.json').read_bytes()
        self.connect_ready()
        self.assertNotIn(('session','start-original-only'),self.backend.actions)
        self.assertEqual(self.backend.units['controller']['ActiveState'],'inactive')
        self.assertTrue(self.op().run()['context_ready'])
        self.assertIn(('session','start-original-only'),self.backend.actions)
        self.backend.settle_probe()
        self.op().run();r=self.op().run()
        self.assertTrue(r['settled']);self.assertEqual(r['state'],'connected')
        self.assertEqual(before,(self.home/'workshop.json').read_bytes())
        self.assertFalse((self.home/'installation-updates/gate.json').exists())
    def test_lost_disconnect_ack_status_returns_receipt_without_effects(self):
        self.disconnect();calls=list(self.backend.actions)
        self.assertEqual(self.op().run()['state'],'disconnected')
        self.assertEqual(self.backend.actions,calls)
        self.assertEqual(self.op('disconnect').run()['state'],'disconnected')
        with self.assertRaises(ContinuityError):self.op('connect')
    def test_lost_restore_ack_never_reloads_or_compares_new_work(self):
        self.disconnect();self.connect_settle();calls=list(self.backend.actions)
        durable_write(self.home/'session.json',{'id':'legitimate-new-work'})
        self.assertTrue(self.op().run()['settled']);self.assertEqual(calls,self.backend.actions)
    def test_unknown_request_status_never_starts_anything(self):
        self.assertEqual(self.op().run()['state'],'unknown');self.assertEqual(self.backend.actions,[])
    def test_status_of_connected_busy_agent_is_not_a_disconnect(self):
        self.backend.body['busy']=True
        self.assertEqual(self.op(identifier=None).run()['state'],'connected')
        self.assertEqual(self.backend.actions,[])
    def test_bad_revision_and_request_reuse_rejected(self):
        self.disconnect();self.cfg['service_connection']['revision']='b'*64
        with self.assertRaises(ValueError):self.op()
    def test_independent_mask_not_removed(self):
        self.backend.units['controller']['LoadState']='masked'
        with self.assertRaises(NotIdle):self.op('connect').run()
        self.assertEqual(self.backend.actions,[])
    def test_changed_world_prevents_original_session_probe(self):
        self.disconnect();self.backend.body['position']['x']=900
        with self.assertRaises(ContinuityError):self.connect_ready()
        self.assertNotIn(('session','start-original-only'),self.backend.actions)
        self.assertEqual(self.backend.units['controller']['ActiveState'],'inactive')
    def test_failed_original_load_disconnects_and_settles_failure(self):
        self.disconnect();self.connect_ready();self.op().run();self.backend.settle_probe(False)
        for _ in range(5):r=self.op().run()
        self.assertTrue(r['settled']);self.assertTrue(r['failed']);self.assertEqual(r['state'],'disconnected')
        self.assertEqual(self.backend.units['controller']['ActiveState'],'inactive')
        self.assertEqual(read(self.home/'session.json'),{'id':'original-session'})
    def test_unknown_probe_launch_is_never_repeated(self):
        self.disconnect();self.connect_ready()
        with patch.object(self.backend,'start_probe',side_effect=OSError('lost dispatch acknowledgement')):
            with self.assertRaises(OSError):self.op().run()
        r=self.op().run();self.assertEqual(r['state'],'unknown');self.assertFalse(r['settled'])
        self.assertEqual(self.backend.units['controller']['ActiveState'],'inactive')
        self.assertNotIn(('session','start-original-only'),self.backend.actions)
    def test_offline_update_defers_without_rejoining_or_removing_gate(self):
        self.disconnect();gate=(self.home/'installation-updates/gate.json').read_bytes()
        tx=str(uuid.uuid4());e={'id':str(uuid.uuid4()),'participant':'minecraft','plan':{
            'schema':1,'transaction_id':tx,'operation':'apply','components':['engine']}}
        p=Participant(self.cfg,e,self.backend);calls=list(self.backend.actions)
        self.assertFalse(p.prepare()['ready']);self.assertTrue(p.verify('unchanged')['verified'])
        self.assertTrue(p.restore('unchanged')['restored']);self.assertEqual(calls,self.backend.actions)
        self.assertEqual(gate,(self.home/'installation-updates/gate.json').read_bytes())
    def test_connect_already_live_does_not_start_overlapping_session_check(self):
        self.backend.body['busy']=True
        r=self.op('connect').run()
        self.assertTrue(r['settled']);self.assertEqual(r['state'],'connected')
        self.assertEqual(self.backend.actions,[])

    def test_service_active_without_join_never_confirms_connected(self):
        self.disconnect();self.connect_ready();self.op().run();self.backend.settle_probe()
        self.op().run()  # Release listener after verified world/session.
        self.backend.body['ready']=False
        r=self.op().run()
        self.assertFalse(r['settled']);self.assertEqual(r['state'],'unknown')
        self.assertEqual(self.backend.actions.count(('session','start-original-only')),1)

    def test_lost_stop_dispatch_does_not_repeat_even_if_service_is_still_active(self):
        self.op('disconnect').run();self.ack()
        with patch.object(self.backend,'action',side_effect=OSError('dispatch unknown')):
            with self.assertRaises(OSError):self.op().run()
        for _ in range(3):self.assertFalse(self.op().run()['settled'])
        self.assertEqual(self.backend.actions,[])
        self.assertTrue((self.home/'installation-updates/gate.json').exists())

    def test_accepted_request_waits_for_other_update_then_status_advances(self):
        tx=str(uuid.uuid4());root=Path(self.cfg['state']);durable_write(root/'active.json',{'transaction_id':tx})
        durable_write(root/'transactions'/(tx+'.json'),{'phase':'ready'})
        self.assertFalse(self.op('disconnect').run()['settled']);self.assertEqual(self.backend.actions,[])
        durable_write(root/'transactions'/(tx+'.json'),{'phase':'restored'})
        self.op().run();self.ack()
        for _ in range(5):r=self.op().run()
        self.assertEqual(r['state'],'disconnected');self.assertTrue(r['settled'])



class ProbeJobTests(unittest.TestCase):
    def test_actual_sdk_child_checks_used_and_unused_sessions_without_prompt(self):
        import hashlib,shutil,subprocess,sys
        from installation_connection import Backend
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);(home/'app').mkdir()
            source=Path(__file__).resolve().parents[1]
            for name in ('acp_client.py','prompt_lifecycle.py'):
                shutil.copy2(source/name,home/'app'/name)
            log=home/'protocol.jsonl'
            cfg={'control_port':1234,'token':'disposable'}
            endpoint={'command':[sys.executable,str(Path(__file__).with_name('session_probe_fixture.py'))],
                      'cwd':str(home),'env':{'PROBE_LOG':str(log)}}
            durable_write(home/'config.json',cfg);durable_write(home/'endpoint.json',endpoint)
            bound={**endpoint,'mcp_servers':[{'type':'http','name':'minecraft','url':'http://127.0.0.1:1234/mcp',
                    'headers':[{'name':'Authorization','value':'Bearer disposable'}]}]}
            saved={'session':'original-used','binding':hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()}
            for present in (True,False):
                if present:durable_write(home/'session.json',saved)
                else:(home/'session.json').unlink();log.unlink()
                result=home/('result-'+str(present)+'.json')
                subprocess.run([sys.executable,str(source/'connection_session_job.py'),'--home',str(home),'--result',str(result)],check=True,timeout=10)
                r=read(result);self.assertTrue(r['verified']);self.assertEqual(r['saved_session_present'],present)
                events=[json.loads(l) for l in log.read_text().splitlines()]
                self.assertEqual(events,[{'action':'initialize'}]+([{'action':'load','session':'original-used'}] if present else []))
                self.assertEqual((home/'session.json').exists(),present)
            endpoint['env']['PROBE_MODE']='initialize-error';durable_write(home/'endpoint.json',endpoint)
            result=home/'failed.json'
            subprocess.run([sys.executable,str(source/'connection_session_job.py'),'--home',str(home),'--result',str(result)],check=True,timeout=10)
            self.assertFalse(read(result)['verified']);self.assertFalse((home/'session.json').exists())


if __name__=='__main__':unittest.main()
