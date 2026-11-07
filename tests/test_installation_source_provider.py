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
                  'node':'/usr/bin/node','npm_cli':'/usr/bin/npm','required_checks':['test'],
                  'channel':'latest-passing-development','task_helper':str(self.home/'task-helpers/agent-runtime')}
        self.cfg['shared_plans']=str(shared/'plans')
        self.provider=FakeProvider(self.cfg);self.plan=self.provider.plan()
        self.envelope={'id':str(uuid.uuid4()),'component':'minecraft','plan':self.plan}
        self.tx=str(uuid.uuid4())
        durable_write(self.provider.root/'transactions'/(self.tx+'.json'),{'phase':'ready','game':True,'config_hash':digest(self.cfg)})
        durable_write(self.home/'installation-updates/gate.json',{'version':1,'transaction_id':self.tx,'closed':True})
        class Idle:
            def services(self):return {k:{'ActiveState':'inactive','MainPID':'0'} for k in ('body','controller')}
        self.patcher=patch('installation_participant.LocalInstallation',lambda cfg:Idle());self.patcher.start();self.addCleanup(self.patcher.stop)
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


if __name__=='__main__':unittest.main()
