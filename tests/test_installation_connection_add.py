import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import installation_connection_add as add
from installation_connection import Connection
from installation_guard import ContinuityError, durable_write, read
from test_installation_connection import Fake


class AddTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.home = self.root/'game'; self.home.mkdir()
        self.game = Fake(self.home)
        (self.home/'session.json').unlink()
        durable_write(self.home/'workshop.json', {'task':None,'turn':None,'inbox':[]})
        self.game.body['task'] = None
        for unit in self.game.units.values():
            unit.update(ActiveState='inactive', MainPID='0', UnitFileState='disabled')
        self.cfg = {'home':str(self.home),'state':str(self.root/'connection-owner'),
                    'units':{'body':'acp-minecraft-body-visit.service','controller':'acp-minecraft-agent-visit.service'},
                    'app':str(self.home/'app'),'venv':str(self.home/'venv')}
        self.config = self.root/'prepared.json'; durable_write(self.config,self.cfg)
        durable_write(self.home/'config.json', {'host':'127.0.0.1','port':25571,
            'control_port':45846,'context_provider_id':'minecraft:visit',
            'incoming_chat_only':True,'human_task_intake':{'enabled':False}})
        durable_write(self.home/'endpoint.json', {'command':['/fixed/engine']})
        self.route_file = self.root/'route.json'
        route_config = self.root/'route-config'; route_config.write_text('owner route')
        self.route = {'schema':1,'home':str(self.home),'checked_at':'2026-11-07T16:00:00Z',
            'config_sha256':add.file_hash(self.home/'config.json'),
            'endpoint_sha256':add.file_hash(self.home/'endpoint.json'),
            'game':{'host':'127.0.0.1','port':25571,'verified':True},
            'context':{'provider_id':'minecraft:visit','url':'http://127.0.0.1:45846',
                       'secret_ref':'owner-secret-ref','runtime_namespace_verified':True},
            'configuration_files':{str(route_config):add.file_hash(route_config)}}
        durable_write(self.route_file,self.route)
        helpers = self.root/'helpers'; helpers.mkdir()
        for name in ('installation_connection.py','connection_state.py','connection_session_job.py',
                     'installation_session_probe.py','installation_participant.py','installation_guard.py',
                     'installation_source_provider.py','installation_retention.py','update_admission.py'):
            (helpers/name).touch()
        self.template = self.root/'add.json'
        durable_write(self.template, {'schema':1,'state':str(self.root/'add-owner'),
            'agent_home':str(self.root/'instance'),'helpers':str(helpers),'python':'/fixed/python',
            'slots':[{'id':'visit','label':'Workshop','config':str(self.config),
                'config_sha256':add.file_hash(self.config),'route_receipt':str(self.route_file),
                'route_sha256':add.file_hash(self.route_file)}]})
        self.c = add.load(self.template)
        self.backend = add.Prerequisites(self.c,self.cfg); self.backend.game = self.game
        self.providers = [{'id':'minecraft:visit','url':'http://127.0.0.1:45846','secret_ref':'owner-secret-ref','enabled':False}]
        self.backend.providers = lambda:copy.deepcopy(self.providers)
        sdk = patch.object(add,'verify_sdk'); self.sdk = sdk.start(); self.addCleanup(sdk.stop)
        self.request = {'schema':1,'service_id':'minecraft','revision':self.c['revision'],
            'action':'add','request_id':str(uuid.uuid4()),'values':{'label':'My visit','server':'visit'}}
        self.original = {n:(self.home/n).read_bytes() for n in ('workshop.json','config.json','endpoint.json')}

    def run_add(self,action='add'):
        return add.operation(self.c,{**self.request,'action':action},self.backend)

    def assert_untouched(self):
        for name,contents in self.original.items():
            self.assertEqual((self.home/name).read_bytes(),contents)
        self.assertFalse((self.home/'session.json').exists())
        self.assertEqual(self.game.actions,[])

    def test_save_offline_and_lost_reply_returns_identical_descriptor(self):
        result = self.run_add()
        self.assertEqual(result['state'],'saved'); self.assertTrue(result['settled'])
        self.assertEqual(result,self.run_add('status')); self.assertEqual(result,self.run_add())
        self.assertEqual(result['connection']['context_provider_ids'],['minecraft:visit'])
        self.assertEqual(read(self.home/'installation-connections/state.json')['phase'],'disconnected')
        self.assert_untouched(); self.sdk.assert_called()

    def test_status_unknown_does_not_start_save(self):
        self.assertFalse(self.run_add('status')['settled'])
        self.assertFalse((Path(self.c['state'])/'operations').exists()); self.assert_untouched()

    def test_interrupted_file_save_recovers_same_operation_only(self):
        real = add.write_once
        def crash(path,value):
            real(path,value)
            if str(path).endswith('gate.json'): raise OSError('crash after gate write')
        with patch.object(add,'write_once',side_effect=crash):
            with self.assertRaises(OSError):self.run_add()
        self.assertEqual(self.run_add('status')['state'],'saved'); self.assert_untouched()

    def test_id_reuse_and_slot_conflict_preserve_first_save(self):
        first = self.run_add()
        self.request['values']['label']='Changed'
        with self.assertRaises(ContinuityError):self.run_add('status')
        self.request['request_id']=str(uuid.uuid4())
        self.assertEqual(self.run_add()['state'],'failed')
        self.assertEqual(read(Path(self.cfg['state'])/'saved-connection-config.json')['service_connection']['label'],
                         first['connection']['label']); self.assert_untouched()

    def test_typed_values_and_template_revision_are_enforced(self):
        for change in ({'revision':'bad'},{'values':{'label':'x','server':'unapproved'}},
                       {'values':{'label':'x','server':'visit','host':'elsewhere'}},
                       {'values':{'label':'x'*121,'server':'visit'}},
                       {'values':{'label':'\n','server':'visit'}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                add.operation(self.c,{**self.request,**change},self.backend)
        self.assert_untouched()

    def test_missing_prematurely_enabled_or_changed_context_registration_refused(self):
        for providers in ([],[{**self.providers[0],'enabled':True}],
                          [{**self.providers[0],'url':'http://other'}]):
            self.providers=providers
            self.request['request_id']=str(uuid.uuid4())
            self.assertEqual(self.run_add()['state'],'failed')
        self.assert_untouched()

    def test_changed_route_configuration_refused(self):
        Path(next(iter(self.route['configuration_files']))).write_text('changed')
        self.assertEqual(self.run_add()['state'],'failed'); self.assert_untouched()

    def test_used_session_refused_without_reset(self):
        durable_write(self.home/'session.json',{'session':'used'})
        self.assertEqual(self.run_add()['state'],'failed')
        self.assertEqual(read(self.home/'session.json'),{'session':'used'})
        self.assertEqual(self.game.actions,[])

    def test_active_units_refused(self):
        self.game.units['body'].update(ActiveState='active',MainPID='101')
        result=self.run_add();self.assertEqual(result['state'],'busy');self.assertFalse(result['settled'])
        self.assert_untouched()

    def test_timeout_is_unknown_and_status_reconciles_only_same_request(self):
        import subprocess
        with patch.object(self.backend,'check',side_effect=subprocess.TimeoutExpired('read-only check',5)):
            with self.assertRaises(subprocess.TimeoutExpired):self.run_add()
        journal=read(Path(self.c['state'])/'operations'/(self.request['request_id']+'.json'))
        self.assertNotIn('result',journal)
        self.assertEqual(self.run_add('status')['state'],'saved');self.assert_untouched()

    def test_known_add_failure_has_no_descriptor_and_new_request_can_succeed(self):
        original=list(self.providers);self.providers=[]
        failed=self.run_add();self.assertEqual(failed['state'],'failed');self.assertTrue(failed['settled'])
        self.assertNotIn('connection',failed)
        self.providers=original
        self.assertEqual(self.run_add('status'),failed)
        self.request['request_id']=str(uuid.uuid4())
        self.assertEqual(self.run_add()['state'],'saved');self.assert_untouched()

    def test_existing_task_authority_or_intake_policy_is_not_cleared_for_setup(self):
        cfg=read(self.home/'config.json'); cfg['human_task_intake']['enabled']=True
        durable_write(self.home/'config.json',cfg)
        route={**self.route,'config_sha256':add.file_hash(self.home/'config.json')}
        with self.assertRaisesRegex(ContinuityError,'task-intake'):
            self.backend.check(route)
        self.assertTrue(read(self.home/'config.json')['human_task_intake']['enabled'])
        cfg['human_task_intake']['enabled']=False;durable_write(self.home/'config.json',cfg)
        route['config_sha256']=add.file_hash(self.home/'config.json')
        durable_write(self.home/'workshop.json',{'task':{'id':'old','status':'expired'},'turn':None})
        with self.assertRaisesRegex(ContinuityError,'unused'):
            self.backend.check(route)
        self.assertEqual(read(self.home/'workshop.json')['task']['id'],'old')

    def test_shared_lock_directory_is_rejected(self):
        template=read(self.template);template['state']=self.cfg['state']
        durable_write(self.template,template)
        with self.assertRaisesRegex(ValueError,'separate owner state'):
            add.load(self.template)

    def test_symlink_output_never_overwrites_target(self):
        target = self.root/'target'; durable_write(target,{'keep':True})
        link = self.root/'link'; link.symlink_to(target)
        with self.assertRaises(ContinuityError):add.write_once(link,{'keep':True})
        self.assertEqual(read(target),{'keep':True})

    def test_enrollment_has_only_fixed_choices_and_no_endpoint_fields(self):
        service = add.enrollment(self.c,self.template)
        self.assertEqual([f['name'] for f in service['add']['fields']],['label','server'])
        self.assertEqual(service['add']['fields'][1]['choices'],[{'value':'visit','label':'Workshop'}])
        self.assertEqual(set(service['add_commands']),{'add','status'})

    def test_new_offline_save_can_connect_without_creating_session(self):
        result=self.run_add(); cfg=read(Path(self.cfg['state'])/'saved-connection-config.json')
        request={'schema':1,'action':'connect','connection_id':result['connection']['id'],
                 'revision':result['connection']['revision'],'request_id':str(uuid.uuid4())}
        self.game.prepared_context_ready=lambda:False
        pending=Connection(cfg,request,self.game).run()
        self.assertFalse(pending['settled']);self.assertIn('Owner setup',pending['message'])
        self.assertEqual(self.game.actions,[])
        self.game.prepared_context_ready=lambda:True
        request['action']='status'
        for _ in range(12):
            output=Connection(cfg,request,self.game).run(); request['action']='status'
            if getattr(self.game,'probe_path',None):
                durable_write(self.game.probe_path,{'verified':True,'initialized':True,
                    'saved_session_present':False,'saved_session_loaded':False,
                    'new_session_created':False,'prompt_sent':False})
            if output['settled']:break
        self.assertEqual(output['state'],'connected');self.assertTrue(output['settled'])
        self.assertFalse((self.home/'session.json').exists())
        self.assertEqual((self.home/'workshop.json').read_bytes(),self.original['workshop.json'])

    def test_prepared_connect_checks_actual_registration_read_only(self):
        import json
        from types import SimpleNamespace
        from installation_connection import Backend
        self.run_add();cfg=read(Path(self.cfg['state'])/'saved-connection-config.json')
        backend=Backend(cfg)
        for changed,expected in (({'enabled':False},False),({'enabled':True},True),
                                 ({'enabled':True,'url':'http://changed'},False)):
            response=SimpleNamespace(stdout=json.dumps({'providers':[{**self.providers[0],**changed}]}))
            with patch('installation_connection.subprocess.run',return_value=response) as command:
                self.assertEqual(backend.prepared_context_ready(),expected)
                self.assertEqual(command.call_args.args[0][-3:],['api','GET','context/providers'])
        self.assert_untouched()


if __name__=='__main__':unittest.main()
