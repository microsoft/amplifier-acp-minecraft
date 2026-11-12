import copy
import json
import os
import sys
import tempfile
import unittest
import uuid
import io
from pathlib import Path
from unittest.mock import patch
from installation_guard import ContinuityError, durable_write, read, digest
from installation_source_provider import Provider, SDK_URL, fingerprint, verify_sdk
from installation_enrollment import registration

SDK='9853d8b514d6340000bcbd01ec07808436db80cf'


class FakeProvider(Provider):
    def candidate(self):return 'b'*40,{'test':{'id':1,'conclusion':'success'}}
    def build(self,revision,previous,stage):
        (stage/'app').mkdir(parents=True);(stage/'app/body.cjs').write_text('candidate')
        (stage/'app/requirements.txt').write_text(f'agent-client-protocol @ git+{SDK_URL}@{SDK}\n')
        dist=stage/'venv/lib/python3.12/site-packages/agent_client_protocol-0.12.1.dist-info'
        dist.mkdir(parents=True);durable_write(dist/'direct_url.json',{'url':SDK_URL,'vcs_info':{'vcs':'git','commit_id':SDK}})
        return verify_sdk(stage/'venv',stage/'app')


class SourceProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.home=self.root/'game';self.home.mkdir()
        shared=self.root/'shared';(shared/'plans').mkdir(parents=True)
        durable_write(shared/'state.json',{'state':'checking','transaction':None})
        for name in ('app','venv'):
            (self.home/name).mkdir();(self.home/name/'original').write_text(name)
        durable_write(self.home/'app-source.json',{'revision':'a'*40,'private_label':'preserve'})
        durable_write(self.home/'workshop.json',{'task':{'turns':8,'max_turns':7},'unknown':['keep']})
        self.cfg={'home':str(self.home),'state':str(self.root/'owner'),
                  'app':str(self.home/'app'),'venv':str(self.home/'venv'),'python':str(Path(sys.executable).resolve()),
                  'node':sys.executable,'npm_cli':sys.executable,'required_checks':['test'],
                  'channel':'latest-passing-development','task_helper':str(self.home/'task-helpers/agent-runtime')}
        self.cfg['shared_plans']=str(shared/'plans')
        self.provider=FakeProvider(self.cfg);self.plan=self.provider.plan()
        self.envelope={'id':str(uuid.uuid4()),'component':'minecraft','plan':self.plan}
        self.tx=str(uuid.uuid4())
        durable_write(self.provider.root/'transactions'/(self.tx+'.json'),{'phase':'ready','game':True,'config_hash':digest(self.cfg)})
        durable_write(self.home/'installation-updates/gate.json',{'version':1,'transaction_id':self.tx,'closed':True})
        class Idle:
            def services(self):return {k:{'ActiveState':'inactive','MainPID':'0'} for k in ('body','controller')}
        self.patcher=patch('installation_participant.LocalInstallation',type('IdleInstallation',(Idle,),{'__init__':lambda self,cfg:None}));self.patcher.start();self.addCleanup(self.patcher.stop)
    def test_supplied_service_backend_keeps_gate_checks_and_never_constructs_systemd_driver(self):
        class Services:
            def __init__(self):self.active=False;self.reads=0
            def services(self):
                self.reads+=1
                return {k:{'ActiveState':'active' if self.active else 'inactive','MainPID':'123' if self.active else '0'} for k in ('body','controller')}
        backend=Services()
        with patch('installation_participant.LocalInstallation',side_effect=AssertionError('No Linux backend construction')):
            provider=FakeProvider(self.cfg,backend=backend)
            provider.require_prepared(self.tx)
            self.assertEqual(backend.reads,1)
            backend.active=True
            with self.assertRaisesRegex(ContinuityError,'both owned units stopped'):provider.require_prepared(self.tx)
            backend.active=False
            self.home.joinpath('installation-updates/gate.json').unlink()
            with self.assertRaises(FileNotFoundError):provider.require_prepared(self.tx)
        self.assertEqual(read(self.home/'workshop.json')['unknown'],['keep'])

    def test_plan_only_stages_and_records_official_sdk_commit(self):
        self.assertFalse((self.home/'app').is_symlink());self.assertEqual(self.provider.status()['version'],'a'*40)
        self.assertEqual(read(Path(self.plan['stage'])/'manifest.json')['sdk']['commit'],SDK)
    def test_apply_verify_and_rollback_never_restore_old_workshop_or_policy(self):
        before=(self.home/'workshop.json').read_bytes()
        self.assertTrue(self.provider.apply(self.envelope,self.tx)['verified'])
        self.assertEqual(self.provider.status()['version'],'b'*40)
        self.assertTrue(self.provider.apply(self.envelope,self.tx)['verified'])
        self.provider.rollback(self.envelope,self.tx);self.provider.rollback(self.envelope,self.tx)
        self.assertEqual(self.provider.status()['version'],'a'*40)
        self.assertEqual((self.home/'workshop.json').read_bytes(),before)
        self.assertEqual(read(self.home/'app-source.json')['private_label'],'preserve')
    def test_plan_tamper_and_staged_byte_tamper_fail_before_swap(self):
        changed=copy.deepcopy(self.envelope);changed['plan']['stage']=str(self.root/'elsewhere')
        with self.assertRaises((ContinuityError,ValueError)):self.provider.apply(changed,self.tx)
        (Path(self.plan['stage'])/'app/body.cjs').write_text('tampered')
        with self.assertRaises(ContinuityError):self.provider.apply(self.envelope,self.tx)
        self.assertFalse((self.home/'app').is_symlink())
    def test_changed_installed_source_or_missing_gate_blocks_apply(self):
        self.home.joinpath('installation-updates/gate.json').unlink()
        with self.assertRaises(FileNotFoundError):self.provider.apply(self.envelope,self.tx)
        durable_write(self.home/'installation-updates/gate.json',{'version':1,'transaction_id':self.tx,'closed':True})
        (self.home/'app/original').write_text('local change')
        with self.assertRaises(ContinuityError):self.provider.apply(self.envelope,self.tx)
    def test_crash_after_first_exchange_rolls_back_without_replaying(self):
        rename=os.rename
        def fail_second(src,dst):
            if Path(src)==self.home/'venv':raise OSError('injected crash')
            return rename(src,dst)
        with patch('installation_source_provider.os.rename',fail_second):
            with self.assertRaises(OSError):self.provider.apply(self.envelope,self.tx)
        with self.assertRaises(ContinuityError):self.provider.apply(self.envelope,self.tx)
        self.provider.rollback(self.envelope,self.tx)
        self.assertFalse((self.home/'app').is_symlink());self.assertFalse((self.home/'venv').is_symlink())
    def test_rollback_before_any_mutation_has_a_verifiable_unchanged_receipt(self):
        self.assertTrue(self.provider.rollback(self.envelope,self.tx)['verified'])
        self.assertTrue(self.provider.verify(self.envelope)['verified'])
        self.assertEqual(self.provider.status()['version'],'a'*40)
    def test_corrupted_candidate_can_still_restore_verified_previous_code(self):
        self.provider.apply(self.envelope,self.tx)
        (Path(self.plan['stage'])/'app/body.cjs').write_text('damaged')
        with self.assertRaises(ContinuityError):self.provider.verify(self.envelope)
        with self.assertRaises(ContinuityError):self.provider.status()
        self.assertTrue(self.provider.rollback(self.envelope,self.tx)['verified'])
    def test_private_source_metadata_is_preserved_and_verified(self):
        self.provider.apply(self.envelope,self.tx)
        marker=read(self.home/'app-source.json');marker['private_label']='unexpected';durable_write(self.home/'app-source.json',marker)
        with self.assertRaises(ContinuityError):self.provider.verify(self.envelope)
    def test_unknown_pointer_during_rollback_is_not_deleted(self):
        self.provider.apply(self.envelope,self.tx)
        (self.home/'app').unlink();(self.home/'app').mkdir();(self.home/'app/other').write_text('keep')
        with self.assertRaises(ContinuityError):self.provider.rollback(self.envelope,self.tx)
        self.assertEqual((self.home/'app/other').read_text(),'keep')
    def test_rollback_requiesces_body_started_only_for_verification(self):
        from test_installation_participant import FakeInstallation
        self.provider.apply(self.envelope,self.tx)
        backend=FakeInstallation(self.home);baseline=backend.capture()
        backend.action('controller','stop')
        durable_write(self.provider.root/'transactions'/(self.tx+'.json'),
                      {'phase':'verifying_body','game':True,'config_hash':digest(self.cfg),'baseline':baseline})
        with patch('installation_participant.LocalInstallation',lambda cfg:backend):
            self.provider.rollback(self.envelope,self.tx)
        self.assertEqual(backend.actions,[('controller','stop'),('body','stop')])
        self.assertEqual(self.provider.status()['version'],'a'*40)
    def test_rollback_is_forbidden_after_listener_restoration_starts(self):
        self.provider.apply(self.envelope,self.tx)
        durable_write(self.provider.root/'transactions'/(self.tx+'.json'),
                      {'phase':'restoring','game':True,'config_hash':digest(self.cfg)})
        with self.assertRaises(ContinuityError):self.provider.rollback(self.envelope,self.tx)
        self.assertEqual(self.provider.status()['version'],'b'*40)
    def test_sdk_version_without_exact_direct_url_is_insufficient(self):
        stage=Path(self.plan['stage']);direct=next((stage/'venv').rglob('direct_url.json'))
        value=read(direct);value['vcs_info']['commit_id']='c'*40;durable_write(direct,value)
        with self.assertRaises(ContinuityError):verify_sdk(stage/'venv',stage/'app')
    def test_enrollment_has_separate_helper_and_explicit_no_shared_restart_scope(self):
        helper=Path(self.cfg['task_helper']);helper.parent.mkdir();helper.write_text('existing')
        config=self.root/'config.json';durable_write(config,self.cfg)
        delta=registration(config,Path(__file__).resolve().parent.parent,Path(sys.executable))
        self.assertEqual([c['id'] for c in delta['components']],['minecraft','task-helpers'])
        self.assertEqual(delta['components'][1]['kind'],'runtime')
        for c in delta['components']:self.assertEqual(c['restart_scope'],{'services':[],'instance':False,'slack_homes':[]})
        self.assertEqual(delta['participants'][0]['protocol'],1)
    def test_saved_connection_enrollment_is_explicit_fixed_argv_and_no_dead_add(self):
        helper=Path(self.cfg['task_helper']);helper.parent.mkdir();helper.write_text('existing')
        config=self.root/'config.json';durable_write(config,self.cfg)
        helpers=Path(__file__).resolve().parent.parent
        self.assertNotIn('service_connections',registration(config,helpers,Path(sys.executable)))
        self.cfg['service_connection']={'id':'minecraft-visit','label':'Visit','revision':'c'*64,
            'context_provider_ids':['minecraft:tester:visit']}
        durable_write(config,self.cfg)
        catalog=registration(config,helpers,Path(sys.executable))['service_connections']
        self.assertEqual(catalog['services'],[{'id':'minecraft','label':'Minecraft'}])
        entry=catalog['connections'][0]
        for action in ('status','connect','disconnect'):
            self.assertEqual(entry['commands'][action],[sys.executable,str(helpers/'installation_connection.py'),
                '--config',str(config),action])
        self.assertEqual(entry['revision'],'c'*64)

    def test_enrollment_namespaces_two_connections_and_keeps_shared_scope(self):
        self.cfg.update(participant_id='minecraft-visit',component_ids={'minecraft':'minecraft-visit','task-helpers':'task-helpers-visit'})
        helper=Path(self.cfg['task_helper']);helper.parent.mkdir();helper.write_text('existing')
        config=self.root/'config.json';durable_write(config,self.cfg)
        delta=registration(config,Path(__file__).resolve().parent.parent,Path(sys.executable))
        self.assertEqual([c['id'] for c in delta['components']],['minecraft-visit','task-helpers-visit'])
        participant=delta['participants'][0]
        self.assertEqual(participant['id'],'minecraft-visit')
        self.assertEqual(participant['components'],['minecraft-visit','task-helpers-visit','instance','runtime','engine','container-image'])

    def test_source_plan_accepts_only_its_own_connection_envelope(self):
        self.cfg.update(component_ids={'minecraft':'minecraft-visit','task-helpers':'task-helpers-visit'})
        self.cfg['state']=str(self.root/'owner-visit')
        provider=FakeProvider(self.cfg);plan=provider.plan()
        envelope={'id':str(uuid.uuid4()),'component':'minecraft-visit','plan':plan}
        provider.frozen(envelope)
        envelope['component']='minecraft'
        with self.assertRaises(ValueError):provider.frozen(envelope)

    def test_candidate_requires_success_for_exact_commit(self):
        for status,conclusion,sha in [('in_progress',None,'b'*40),('completed','failure','b'*40),('completed','success','c'*40)]:
            def gh(endpoint):
                if '/check-runs' in endpoint:return {'total_count':1,'check_runs':[{'id':1,'name':'test','head_sha':sha,'status':status,'conclusion':conclusion}]}
                return {'sha':'b'*40}
            with patch.object(self.provider,'gh',gh):
                with self.assertRaises(ContinuityError):Provider.candidate(self.provider)
    def test_public_metadata_does_not_require_a_github_login(self):
        with patch('installation_source_provider.urllib.request.urlopen',return_value=io.BytesIO(b'{"sha":"public"}')) as http, patch('installation_source_provider.run') as command:
            self.assertEqual(self.provider.gh('commits/main'),{'sha':'public'})
            command.assert_not_called()
            self.assertNotIn('Authorization',http.call_args.args[0].headers)
    def test_unsupported_lifecycle_platform_is_not_enrolled(self):
        with patch('installation_enrollment.platform.system',return_value='Darwin'):
            with self.assertRaises(ValueError):registration('/unused','/unused','/unused')



class SourceMarkerTests(unittest.TestCase):
    setUp=SourceProviderTests.setUp
    def test_new_plan_refreshes_exact_file_inventory_and_rollback_preserves_original(self):
        marker=read(self.home/'app-source.json');marker['files']={'removed.py':'old-hash'}
        durable_write(self.home/'app-source.json',marker)
        plan=self.provider.plan();envelope={**self.envelope,'id':str(uuid.uuid4()),'plan':plan}
        self.assertEqual(plan['source_marker_version'],2)
        self.provider.apply(envelope,self.tx)
        installed=read(self.home/'app-source.json')
        self.assertNotIn('removed.py',installed['files'])
        self.assertEqual(installed['files']['body.cjs'],__import__('hashlib').sha256(b'candidate').hexdigest())
        self.assertEqual(installed['private_label'],'preserve')
        self.provider.rollback(envelope,self.tx)
        self.assertEqual(read(self.home/'app-source.json'),marker)
    def test_retained_legacy_plan_keeps_its_marker_contract(self):
        self.envelope['plan'].pop('source_marker_version')
        self.provider.apply(self.envelope,self.tx)
        self.assertNotIn('files',read(self.home/'app-source.json'))
        self.assertTrue(self.provider.verify(self.envelope)['verified'])
        self.provider.rollback(self.envelope,self.tx)

if __name__=='__main__':unittest.main()

class ScreenshotBrowserTests(unittest.TestCase):
    setUp=SourceProviderTests.setUp
    def test_disabled_screenshots_do_not_prepare_browser(self):
        with patch('installation_source_provider.run') as call:
            self.provider.screenshot_browser(self.home/'app',prepare=True)
        call.assert_not_called()
    def test_enabled_browser_is_provisioned_and_checked_with_current_policy(self):
        durable_write(self.home/'config.json',{'screenshots':{'enabled':True}})
        with patch('installation_source_provider.run') as call:
            self.provider.screenshot_browser(self.home/'app',prepare=True)
            self.assertEqual(call.call_args.args[0], [self.cfg['node'],str(self.home/'app/screenshot-browser.cjs'),'prepare'])
            self.provider.screenshot_browser(self.home/'app')
            self.assertEqual(call.call_args.args[0][-1],'check')
        self.assertEqual(self.provider.build_inputs()['screenshot_browser'],{'enabled':True,'browser_path':None})
    def test_custom_browser_policy_is_exact_and_failure_prevents_candidate(self):
        durable_write(self.home/'config.json',{'screenshots':{'enabled':True,'browser_path':'/owner/chromium'}})
        with patch('installation_source_provider.run',side_effect=RuntimeError('launch failed')):
            with self.assertRaisesRegex(RuntimeError,'launch failed'):
                self.provider.screenshot_browser(self.home/'app',prepare=True)
        durable_write(self.home/'config.json',{'screenshots':{'enabled':True,'browser_path':'relative'}})
        with self.assertRaises(ContinuityError):self.provider.build_inputs()
    def test_changed_browser_policy_blocks_frozen_apply_before_swap(self):
        durable_write(self.home/'config.json',{'screenshots':{'enabled':True}})
        with self.assertRaisesRegex(ContinuityError,'policy changed'):
            self.provider.frozen(self.envelope)
        self.assertFalse((self.home/'app').is_symlink())
    def test_real_build_checks_browser_after_assets_and_before_candidate_use(self):
        import tarfile
        durable_write(self.home/'config.json',{'screenshots':{'enabled':True}})
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            value=f'agent-client-protocol @ git+{SDK_URL}@{SDK}\n'.encode()
            info=tarfile.TarInfo('requirements.txt');info.size=len(value);tar.addfile(info,io.BytesIO(value))
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            if 'archive' in argv:return archive.getvalue()
            if '--version' in argv:return 'v22.23.2'
            if any(str(x).endswith('screenshot-browser.cjs') for x in argv):raise RuntimeError('browser unavailable')
            return b''
        with patch('installation_source_provider.run',side_effect=command),patch('installation_source_provider.subprocess.run') as git:
            git.return_value.returncode=0
            with self.assertRaisesRegex(RuntimeError,'browser unavailable'):
                Provider.build(self.provider,'b'*40,'a'*40,self.root/'new-stage')
        self.assertTrue(any('build:screenshots' in argv for argv in calls))
        self.assertFalse(any('venv' in argv for argv in calls));self.assertFalse((self.home/'app').is_symlink())
