"""Domain transaction fixtures; these do not claim actual OS service coverage."""
import copy
import tempfile
import unittest
import uuid
from pathlib import Path

from installation_guard import (ContinuityError, NotIdle, continuity, durable_write,
    native_service, read, require_idle, restore_plan, service_active,
    service_process_identity, service_stopped, snapshot)
from installation_participant import Participant
from installation_connection import Connection


def service(manager='systemd_user', pid=123, active=True, enabled=True):
    role = {'systemd_user':'MainPID', 'launch_agent':'launchd_pid',
            'scheduled_task':'scheduled_task_engine'}[manager]
    identity = ({'pid':pid, 'start_ticks':'10', 'boot_id':'boot'} if manager=='systemd_user'
                else {'pid':pid, 'platform':manager, 'generation':'birth-10'})
    return {'schema':1,'service':{'manager':manager,'name':'owned-controller',
            'definition_path':'/fixed/controller'},'definition':{'sha256':'source'},
            'effective_definition':{'sha256':'effective'},'definition_matches':True,
            'enabled':enabled,'start_allowed':enabled,'masked':False,'loaded':True,
            'active':active,'transitioning':False,
            'processes':[{'role':role,'identity':identity}] if active else [],
            'native':{'opaque':'retained manager evidence'}}


class NativeFixture:
    def __init__(self, home, manager):
        self.home, self.actions = home, []
        self.units={k:service(manager,pid) for k,pid in [('controller',100),('body',101)]}
        for kind in self.units:self.units[kind]['service']['name']=kind
        self.body={'task':{'id':'original','status':'budget_exhausted','turns':8},
            'ready':True,'busy':False,'turn_active':False,
            'action_lease':{'version':1,'lease_id':None,'expires_at':0,'renewable':False},
            'inventory':{'slots':[{'name':'pickaxe','damage':48}],'cursor':None},
            'position':{'x':1,'y':64,'z':3}}
        durable_write(home/'workshop.json',{'task':self.body['task'],'turn':None,
                     'unknown_receipts':['never replay'],'inbox':[]})
        durable_write(home/'session.json',{'id':'original-session'})
    def services(self):return copy.deepcopy(self.units)
    def capture(self):
        body=self.body if service_active(self.units['body']) else None
        return snapshot(self.home,self.services(),body,{**body,'action_sequence':None} if body else None)
    def action(self,kind,action):
        self.actions.append((kind,action));old=self.units[kind]
        old['active']=action=='start'
        if action=='stop':old['processes']=[]
        else:old['processes']=service(old['service']['manager'],200)['processes']
        if old['service']['manager']=='launch_agent':old['loaded']=action=='start'
    def helper(self):return {'static':True}
    def session(self,timeout):
        self.actions.append(('session','load-only'))
        return {'verified':True,'initialized':True,'saved_session_loaded':True,
                'new_session_created':False,'prompt_sent':False}
    def connected(self):return self.body['ready']
    def start_probe(self,path):
        self.actions.append(('session','start-original-only'));self.probe_path=path
        return {'pid':444,'generation':'original-probe'}
    def probe_alive(self,identity):return True
    def settle_probe(self):
        durable_write(self.probe_path,{'verified':True,'initialized':True,
            'saved_session_present':True,'saved_session_loaded':True,
            'new_session_created':False,'prompt_sent':False})


class NativeEvidenceTests(unittest.TestCase):
    def test_raw_native_status_is_retained_not_rewritten_as_systemd(self):
        for manager in ('systemd_user','launch_agent','scheduled_task'):
            state=service(manager);before=copy.deepcopy(state)
            self.assertTrue(native_service(state));self.assertTrue(service_active(state))
            self.assertFalse(service_stopped(state));self.assertEqual(state,before)
            self.assertNotIn('ActiveState',state)

    def test_scheduler_engine_is_not_assumed_to_be_controller(self):
        with self.assertRaisesRegex(ContinuityError,'generation'):
            service_process_identity(service('scheduled_task'))

    def test_original_unknown_state_cannot_be_captured_as_stopped(self):
        for patch in ({'active':None},{'transitioning':True},{'active':False}):
            state=service();state.update(patch)
            with self.assertRaises(NotIdle):restore_plan({'controller':state,'body':state},{'controller':state,'body':state})

    def test_restore_preserves_disable_definition_and_native_identity(self):
        before={k:service('launch_agent') for k in ('body','controller')}
        after=copy.deepcopy(before)
        for state in after.values():state.update(active=False,processes=[],loaded=False)
        self.assertEqual(restore_plan(before,after),{'body':'start','controller':'start'})
        for field,value in [('enabled',False),('masked',True),('start_allowed',False),
                            ('definition',{'sha256':'changed'}),('effective_definition',{}),
                            ('definition_matches',False)]:
            changed=copy.deepcopy(after);changed['controller'][field]=value
            with self.subTest(field=field),self.assertRaises(ContinuityError):restore_plan(before,changed)
        stopped={k:service('scheduled_task',active=False,enabled=False) for k in ('body','controller')}
        self.assertEqual(restore_plan(stopped,stopped),{'body':'leave_stopped','controller':'leave_stopped'})

    def run_transaction(self,manager,components):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'home';home.mkdir();backend=NativeFixture(home,manager)
            cfg={'home':str(home),'state':str(Path(tmp)/'state')}
            env={'id':str(uuid.uuid4()),'participant':'minecraft','plan':{'schema':1,
                 'transaction_id':str(uuid.uuid4()),'operation':'apply','components':components}}
            before=(home/'workshop.json').read_bytes();binding=(home/'session.json').read_bytes()
            p=Participant(cfg,env,backend)
            self.assertFalse(p.prepare()['ready'])
            durable_write(home/'installation-updates/controller-idle.json',{
                'transaction_id':env['plan']['transaction_id'],
                **service_process_identity(backend.units['controller'])})
            for _ in range(5):
                if p.prepare()['ready']:break
            else:self.fail('prepare never settled')
            self.assertTrue(p.verify('applied')['verified'])
            # Lost restore acknowledgment: reload the same durable transaction.
            self.assertTrue(p.restore('applied')['restored']);actions=copy.deepcopy(backend.actions)
            self.assertTrue(Participant(cfg,env,backend).restore('applied')['restored'])
            self.assertEqual(backend.actions,actions)
            self.assertEqual((home/'workshop.json').read_bytes(),before)
            self.assertEqual((home/'session.json').read_bytes(),binding)
            self.assertEqual(backend.actions.count(('session','load-only')),1)
            self.assertFalse(p.gate.exists())
            for state in p.value['baseline']['services'].values():self.assertIn('native',state)

    def test_shared_and_source_transactions_keep_native_evidence_and_receipts(self):
        for manager in ('systemd_user','launch_agent'):
            for components in (['instance'],['minecraft']):
                with self.subTest(manager=manager,components=components):self.run_transaction(manager,components)

    def test_unproved_windows_controller_refuses_before_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'home';home.mkdir();backend=NativeFixture(home,'scheduled_task')
            cfg={'home':str(home),'state':str(Path(tmp)/'state')}
            env={'id':str(uuid.uuid4()),'participant':'minecraft','plan':{'schema':1,
                'transaction_id':str(uuid.uuid4()),'operation':'apply','components':['minecraft']}}
            p=Participant(cfg,env,backend)
            with self.assertRaisesRegex(ContinuityError,'generation'):p.prepare()
            self.assertFalse(p.gate.exists());self.assertFalse(p.path.exists());self.assertEqual(backend.actions,[])

    def test_saved_connection_quiescence_readiness_and_lost_ack_with_native_snapshots(self):
        for manager in ('systemd_user','launch_agent'):
            with self.subTest(manager=manager),tempfile.TemporaryDirectory() as tmp:
                home=Path(tmp)/'home';home.mkdir();backend=NativeFixture(home,manager)
                cfg={'home':str(home),'state':str(Path(tmp)/'owner'),
                    'service_connection':{'id':'minecraft-test','label':'Test',
                        'revision':'a'*64,'context_provider_ids':['minecraft:test']}}
                request=str(uuid.uuid4());before=(home/'workshop.json').read_bytes()
                def op(action='status'):
                    return Connection(cfg,{'schema':1,'connection_id':'minecraft-test',
                        'revision':'a'*64,'action':action,'request_id':request},backend)
                self.assertFalse(op('disconnect').run()['settled'])
                durable_write(home/'installation-updates/controller-idle.json',{
                    'transaction_id':request,**service_process_identity(backend.units['controller'])})
                self.assertFalse(op().run()['settled'])
                quiesced=op().run();self.assertTrue(quiesced['context_quiesced'])
                self.assertTrue(service_active(backend.units['body']))
                for _ in range(6):
                    result=op().run()
                    if result['settled']:break
                self.assertEqual(result['state'],'disconnected');self.assertTrue(result['settled'])
                request=str(uuid.uuid4());op('connect').run()
                for _ in range(6):
                    result=op().run()
                    if result.get('context_ready'):break
                self.assertTrue(result['context_ready'])
                self.assertNotIn(('session','start-original-only'),backend.actions)
                op().run();backend.settle_probe()
                for _ in range(6):
                    result=op().run()
                    if result['settled']:break
                self.assertEqual(result['state'],'connected');self.assertTrue(result['settled'])
                actions=copy.deepcopy(backend.actions)
                self.assertEqual(op().run(),result);self.assertEqual(backend.actions,actions)
                self.assertEqual((home/'workshop.json').read_bytes(),before)
                self.assertEqual(read(home/'session.json'),{'id':'original-session'})

    def test_body_generation_change_remains_a_continuity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);backend=NativeFixture(home,'launch_agent');before=backend.capture()
            backend.units['body']['processes'][0]['identity']['generation']='different'
            with self.assertRaises(ContinuityError):continuity(before,backend.capture())
            for patch in ({'active':None},{'transitioning':True},{'processes':[]},
                          {'processes':[{'identity':{'pid':123}}]}):
                changed=copy.deepcopy(before);changed['services']['body'].update(patch)
                with self.assertRaises(NotIdle):require_idle(changed)

if __name__=='__main__':unittest.main()
