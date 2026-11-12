"""Native registration emits fixed owner commands, never starts or joins."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from installation_enrollment import registration
from installation_guard import durable_write,read
import test_installation_source_provider as source_tests


class NativeEnrollmentTests(unittest.TestCase):
    setUp=source_tests.SourceProviderTests.setUp
    def prepare(self):
        helper=Path(self.cfg['task_helper']);helper.parent.mkdir();helper.write_text('separate pure helper')
        driver=Path(self.cfg['state'])/'driver.json'
        self.cfg['native_platform']={'version':1,'driver':str(self.root/'fixed-driver'),
           'config':str(driver),'python':str(self.home/'venv/bin/python3'),'services':{'body':'body','controller':'controller'}}
        durable_write(driver,{'version':1,'roots':{k:self.cfg[k] for k in ('home','state')},
            'locks':{'installation':str(Path(self.cfg['state'])/'installation.lock')},
            'services':{'body':{'manager':'scheduled_task','name':'Minecraft-body'},'controller':{'manager':'scheduled_task','name':'Minecraft-controller'}}})
        self.config=self.root/'owner-config.json';durable_write(self.config,self.cfg)
        self.helpers=Path(__file__).resolve().parent.parent
    def test_explicit_native_uses_isolated_fixed_entries_with_same_scope(self):
        self.prepare();before=self.home.joinpath('workshop.json').read_bytes()
        with patch('installation_enrollment.platform.system',return_value='Windows'):
            result=registration(self.config,self.helpers,Path(sys.executable))
        commands=result['components'][0]['commands']
        for action,argv in commands.items():
            self.assertEqual(argv,[sys.executable,'-I',str(self.helpers/'native_entry.py'),'source-provider','--config',str(self.config),action])
        self.assertEqual(result['components'][0]['restart_scope'],{'services':[],'instance':False,'slack_homes':[]})
        self.assertEqual(result['components'][1]['kind'],'runtime')
        self.assertEqual(self.home.joinpath('workshop.json').read_bytes(),before)
    def test_mutable_game_python_cannot_run_owner_update_helper(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'outside mutable'):
            registration(self.config,self.helpers,self.home/'venv/bin/python3')
    def test_changed_root_mapping_refuses_enrollment(self):
        self.prepare();p=Path(self.cfg['native_platform']['config']);value=read(p)
        value['roots']['home']=str(self.root/'different');durable_write(p,value)
        with self.assertRaisesRegex(ValueError,'root mapping'):
            registration(self.config,self.helpers,Path(sys.executable))

if __name__=='__main__':unittest.main()
