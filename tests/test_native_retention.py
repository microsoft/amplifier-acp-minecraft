"""Native exchange journals retain rollback targets and uncertain operations."""
from pathlib import Path
import unittest
import uuid
from installation_guard import durable_write
from test_installation_retention import RetentionTests as _Fixture


class NativeRetentionTests(unittest.TestCase):
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    stage=_Fixture.stage
    age=_Fixture.age
    def exchange(self,plan,phase='applied'):
        self.cfg['native_platform']={'version':1}
        operation=str(uuid.uuid4());transaction=str(uuid.uuid4())
        directory=self.keep.root/'native-source'/operation;directory.mkdir(parents=True)
        (directory/'app-baseline').symlink_to(Path(plan['stage'])/'app',target_is_directory=True)
        durable_write(self.keep.root/'native-source-receipts'/(operation+'.json'),
          {'phase':phase,'transaction':transaction,'entries':{'app':{},'venv':{}}})
        durable_write(self.keep.root/'transactions'/(transaction+'.json'),{'phase':'restored'})
        return directory,transaction
    def test_native_rollback_stage_is_retained_after_shared_plan_removal(self):
        plan=self.stage();self.age(plan);self.exchange(plan)
        self.assertEqual(self.provider.cleanup()['pruned'],[])
        self.assertTrue(Path(plan['stage']).exists())
    def test_partial_native_exchange_blocks_all_collection(self):
        plan=self.stage();self.age(plan);self.exchange(plan,'preparing')
        self.assertIn('held',self.provider.cleanup());self.assertTrue(Path(plan['stage']).exists())
    def test_unjournaled_native_artifact_blocks_collection(self):
        plan=self.stage();self.age(plan);self.exchange(plan)
        (self.keep.root/'native-source'/str(uuid.uuid4())).mkdir()
        self.assertIn('held',self.provider.cleanup());self.assertTrue(Path(plan['stage']).exists())

# Do not rediscover the imported fixture's tests in this module.
del _Fixture
if __name__=='__main__':unittest.main()
