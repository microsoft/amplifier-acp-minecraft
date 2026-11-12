import copy
import json
import shutil
import sys
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from installation_guard import ContinuityError, durable_write, installation_lock, read
from installation_source_provider import fingerprint
from test_installation_source_provider import FakeProvider


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'game';self.home.mkdir()
        for key in ('app','venv'):
            (self.home/key).mkdir();(self.home/key/'user-baseline').write_text(key)
        durable_write(self.home/'app-source.json',{'revision':'a'*40})
        self.authority={'task':{'id':'original','turns':8},'unknown':['never replay']}
        durable_write(self.home/'workshop.json',self.authority)
        self.plans=self.root/'shared/plans';self.plans.mkdir(parents=True)
        durable_write(self.plans.parent/'state.json',{'state':'checking','transaction':None})
        self.cfg={'home':str(self.home),'state':str(self.root/'owner'),
            'app':str(self.home/'app'),'venv':str(self.home/'venv'),
            'python':str(Path(sys.executable).resolve()),'node':sys.executable,'npm_cli':sys.executable,
            'channel':'latest-passing-development','required_checks':['test'],'shared_plans':str(self.plans)}
        self.provider=FakeProvider(self.cfg);self.keep=self.provider.retention

    def tearDown(self):
        self.assertEqual(read(self.home/'workshop.json'),self.authority)

    def stage(self, revision='b'*40):
        with patch.object(self.provider,'candidate',return_value=(revision,{'test':{'id':1,'conclusion':'success'}})):
            return self.provider.plan()

    def age(self, plan):
        self.keep.mark('stage',Path(plan['stage']).name,last_offered=time.time()-172800)

    def retain(self, envelope):
        folder=self.plans/envelope['id'];folder.mkdir()
        durable_write(folder/'minecraft.provider.json',envelope)
        durable_write(folder/'plan.json',{'components':[{'id':'minecraft','available':True}]})
        return folder

    def apply(self, plan):
        envelope={'id':str(uuid.uuid4()),'component':'minecraft','plan':plan};tx=str(uuid.uuid4())
        with patch.object(self.provider,'require_prepared'):
            self.provider.apply(envelope,tx)
        durable_write(self.keep.root/'transactions'/(tx+'.json'),{'phase':'restored'})
        return envelope

    def test_namespaced_retained_plan_protects_only_own_stage(self):
        self.cfg['component_ids']={'minecraft':'minecraft-visit','task-helpers':'task-helpers-visit'}
        plan=self.stage();self.age(plan)
        identifier=str(uuid.uuid4());folder=self.plans/identifier;folder.mkdir()
        durable_write(folder/'minecraft-visit.provider.json',{'id':identifier,'component':'minecraft-visit','plan':plan})
        durable_write(folder/'plan.json',{'components':[{'id':'minecraft-visit','available':True}]})
        self.provider.cleanup()
        self.assertTrue(Path(plan['stage']).exists())
        (folder/'minecraft-visit.provider.json').unlink()
        with self.assertRaises(ContinuityError):self.keep.references()

    def test_repeated_busy_checks_reuse_immutable_verified_stage(self):
        first=self.stage();path=Path(first['stage']);manifest=(path/'manifest.json').read_bytes()
        for _ in range(5):self.assertEqual(self.stage()['stage'],first['stage'])
        self.assertEqual((path/'manifest.json').read_bytes(),manifest)
        self.assertEqual(len(list((self.keep.root/'stages').iterdir())),1)

    def test_failed_partial_build_removed_immediately_with_receipt(self):
        outside=self.root/'user-file';outside.write_text('keep')
        def fail(revision,previous,stage):
            stage.mkdir(parents=True);(stage/'partial').write_text('regenerable')
            (stage/'outside').symlink_to(outside)
            raise RuntimeError('npm or pip failed')
        with patch.object(self.provider,'build',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'npm or pip'):self.stage()
        self.assertEqual(list((self.keep.root/'stages').iterdir()),[])
        receipt=read(next(self.keep.records.glob('stage-*.json')))
        self.assertEqual(receipt['state'],'pruned');self.assertEqual(receipt['reason'],'failed_build_unreferenced')
        self.assertEqual(outside.read_text(),'keep')

    def test_native_errors_preserve_primary_failure_without_staging_recovery(self):
        # Binding contract doubles; actual Session transport/lock loss is
        # qualified separately. No shared Python dependency for legacy installs.
        class DriverError(RuntimeError):
            def __init__(self,code):self.code=code;super().__init__(code)
        class Unknown(DriverError):pass
        class Refused(DriverError):pass
        for error in (DriverError('transport_timeout'),Unknown('transport_timeout'),
                      Unknown('correlated_unknown'),Refused('predispatch')):
            with self.subTest(error=type(error).__name__,code=error.code):
                cfg={**self.cfg,'native_platform':{'version':1},'state':str(self.root/str(uuid.uuid4()))}
                provider=FakeProvider(cfg);keep=provider.retention
                stages=[]
                def fail(revision,previous,stage):
                    stage.mkdir(parents=True);(stage/'partial').write_text('retain uncertain output')
                    stages.append(stage)
                    raise error
                with patch.dict(sys.modules,{'constellation_native':types.SimpleNamespace(DriverError=DriverError)}), \
                     patch.object(provider,'build',side_effect=fail) as build, \
                     patch.object(keep,'mark',wraps=keep.mark) as mark, \
                     patch.object(provider,'cleanup',wraps=provider.cleanup) as cleanup:
                    with self.assertRaises(DriverError) as caught:
                        with installation_lock(provider.root/'installation.lock'):
                            provider.plan()
                    self.assertIs(caught.exception,error)
                    self.assertEqual(build.call_count,1)
                    self.assertEqual(mark.call_count,1)
                    self.assertEqual(mark.call_args.kwargs['state'],'building')
                    cleanup.assert_called_once_with()  # Only pre-build collection.
                # Reacquire and inspect the same intent, without calling plan or
                # declaring uncertain work failed. The partial stage survives.
                with installation_lock(provider.root/'installation.lock'):
                    record=keep.owned('stage',stages[0].name)
                    self.assertEqual(record['state'],'building')
                    self.assertNotIn('error_type',record)
                    self.assertEqual((stages[0]/'partial').read_text(),'retain uncertain output')

    def test_failed_build_that_became_referenced_is_preserved(self):
        def fail(revision,previous,stage):
            stage.mkdir(parents=True);(stage/'partial').write_text('keep')
            self.retain({'id':str(uuid.uuid4()),'component':'minecraft','plan':{'available':True,'stage':str(stage)}})
            raise RuntimeError('build failed')
        with patch.object(self.provider,'build',side_effect=fail):
            with self.assertRaises(RuntimeError):self.stage()
        self.assertEqual(len(list((self.keep.root/'stages').iterdir())),1)

    def test_old_unreferenced_stage_removed_but_recent_and_unmarked_preserved(self):
        old=self.stage();recent=self.stage('c'*40);self.age(old)
        user=self.keep.root/'stages'/str(uuid.uuid4());user.mkdir();(user/'user-file').write_text('keep')
        result=self.provider.cleanup()
        self.assertFalse(Path(old['stage']).exists());self.assertTrue(Path(recent['stage']).exists())
        self.assertEqual((user/'user-file').read_text(),'keep');self.assertEqual(len(result['pruned']),1)

    def test_all_retained_shared_plans_and_rollback_plan_protect_stages(self):
        stages=[self.stage(c*40) for c in ('b','c','d','e')]
        envelopes=[{'id':str(uuid.uuid4()),'component':'minecraft','plan':p} for p in stages]
        for e in envelopes:self.retain(e);self.age(e['plan'])
        durable_write(self.plans.parent/'state.json',{'state':'available','rollback_plan_id':envelopes[0]['id'],'plan_id':envelopes[-1]['id']})
        self.assertEqual(self.provider.cleanup()['pruned'],[])
        self.assertTrue(all(Path(p['stage']).exists() for p in stages))

    def test_current_stage_and_real_baseline_backup_survive_managed_link_pruning(self):
        first=self.stage();baseline=self.apply(first)
        second=self.stage('c'*40);managed=self.apply(second);folder=self.retain(managed)
        self.age(first);self.age(second)
        self.provider.cleanup();self.assertTrue(Path(first['stage']).exists())
        shutil.rmtree(folder)  # The shared updater, not this provider, expires its plan.
        self.provider.cleanup()
        self.assertFalse(Path(first['stage']).exists());self.assertTrue(Path(second['stage']).exists())
        self.assertTrue((self.keep.root/'backups'/baseline['id']/'app/user-baseline').exists())
        self.assertFalse((self.keep.root/'backups'/managed['id']).exists())

    def test_uncertain_provider_and_participant_transactions_block_cleanup_and_new_builds(self):
        plan=self.stage();self.age(plan)
        for folder,value in [('provider-receipts',{'state':'applying'}),('transactions',{'phase':'verifying_body'})]:
            path=self.keep.root/folder/(str(uuid.uuid4())+'.json');durable_write(path,value)
            self.assertIn('held',self.provider.cleanup());self.assertTrue(Path(plan['stage']).exists())
            with self.assertRaises(ContinuityError):self.stage('c'*40)
            path.unlink()

    def test_missing_or_malformed_shared_roots_never_allow_collection(self):
        plan=self.stage();self.age(plan);state=self.plans.parent/'state.json'
        original=state.read_bytes()
        for content in ('bad json','null','{"state":"checking","rollback_plan_id":"missing"}'):
            state.write_text(content);self.assertIn('held',self.provider.cleanup())
            self.assertTrue(Path(plan['stage']).exists())
        state.write_bytes(original);self.cfg['shared_plans']=str(self.root/'missing')
        self.assertIn('held',self.provider.cleanup());self.assertTrue(Path(plan['stage']).exists())

    def test_changed_staged_bytes_and_interrupted_build_are_not_deleted(self):
        plan=self.stage();self.age(plan);path=Path(plan['stage']);(path/'app/body.cjs').write_text('user change')
        identifier=str(uuid.uuid4());interrupted=self.keep.path('stage',identifier);interrupted.mkdir()
        self.keep.mark('stage',identifier,state='building',created_at=0)
        self.provider.cleanup();self.assertEqual((path/'app/body.cjs').read_text(),'user change')
        self.assertTrue(interrupted.exists())

    def test_stage_symlink_cannot_delete_external_directory(self):
        plan=self.stage();self.age(plan);path=Path(plan['stage']);external=self.root/'outside'
        path.rename(external);path.symlink_to(external,target_is_directory=True)
        self.assertIn('held',self.provider.cleanup());self.assertTrue((external/'app/body.cjs').exists())

    def test_late_reference_is_detected_before_deletion(self):
        plan=self.stage();self.age(plan);original=self.keep.references;calls=0
        def raced():
            nonlocal calls
            calls+=1;value=original()
            if calls>=3:value[0].add(Path(plan['stage']).name)
            return value
        with patch.object(self.keep,'references',side_effect=raced):
            self.assertIn('held',self.provider.cleanup())
        self.assertTrue(Path(plan['stage']).exists())

    def test_changed_build_inputs_and_tampering_never_reuse_old_candidate(self):
        first=self.stage();self.cfg['required_checks']=['test','other']
        second=self.stage();self.assertNotEqual(first['stage'],second['stage'])
        (Path(second['stage'])/'app/body.cjs').write_text('changed')
        third=self.stage();self.assertNotEqual(second['stage'],third['stage'])

    def test_shared_active_transaction_preserves_everything(self):
        plan=self.stage();self.age(plan)
        durable_write(self.plans.parent/'state.json',{'state':'checking','transaction':{'id':'unknown'}})
        self.assertIn('held',self.provider.cleanup());self.assertTrue(Path(plan['stage']).exists())

    def test_source_checks_require_explicit_retained_plan_enrollment(self):
        del self.cfg['shared_plans']
        with self.assertRaisesRegex(ContinuityError,'shared_plans'):self.stage()


    def test_interrupted_build_blocks_another_allocation(self):
        identifier=str(uuid.uuid4());self.keep.path('stage',identifier).mkdir(parents=True)
        self.keep.mark('stage',identifier,state='building',created_at=0)
        with self.assertRaises(ContinuityError):self.stage()
        self.assertEqual(len(list((self.keep.root/'stages').iterdir())),1)

    def test_changed_manifest_and_extra_user_files_are_preserved(self):
        first=self.stage();second=self.stage('c'*40)
        for plan in (first,second):self.age(plan)
        manifest=Path(first['stage'])/'manifest.json';value=read(manifest)
        value['user_note']='retain';durable_write(manifest,value)
        (Path(second['stage'])/'notes.txt').write_text('user data')
        self.assertEqual(self.provider.cleanup()['pruned'],[])
        self.assertTrue(manifest.exists())
        self.assertTrue((Path(second['stage'])/'notes.txt').exists())
