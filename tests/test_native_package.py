"""Published-package staging tests: no subprocess, model, or installed mutation."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from installation_guard import ContinuityError
from installation_native_package import stage_package

PIN='9853d8b514d6340000bcbd01ec07808436db80cf'
REV='b'*40


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stage=self.root/'stage'
        self.python=self.root/'python';self.node=self.root/'node'
        self.python.write_bytes(b'python');self.node.write_bytes(b'node')
        self.driver=self.root/'driver';self.driver.write_bytes(b'driver')
        self.files={'python/bin/python3':b'python','node/node':b'node','task-helper/helper':b'helper',
          'app/requirements.txt':('agent-client-protocol @ git+https://github.com/agentclientprotocol/python-sdk.git@'+PIN+'\n').encode(),
          'python/lib/python3.12/site-packages/agent_client_protocol-0.12.1.dist-info/direct_url.json':json.dumps(
             {'url':'https://github.com/agentclientprotocol/python-sdk.git','vcs_info':{'vcs':'git','commit_id':PIN}}).encode()}
        self.manifest={'schema':1,'target':'linux-arm64','source_commit':REV,'source_clean':True,'sdk_commit':PIN,
          'native_platform':{'repository':'microsoft/amplifier-constellation','driver_sha256':hashlib.sha256(b'driver').hexdigest()},
          'commands':{'python':'python/bin/python3','node':'node/node','task_helper':'task-helper/helper'}}
        self.release={'draft':False,'prerelease':False,'tag_name':'v1.0.0','assets':[]}
        self.calls=[];self.screens=[]
        self.provider=SimpleNamespace(c={'channel':'stable','python':str(self.python),'node':str(self.node),
             'native_platform':{'environment_python':'bin/python3','driver':str(self.driver)}},gh=self.gh,
             screenshot_browser=lambda p:self.screens.append(p))
        self.tree='c'*40;self.comparison='ahead';self.tag_revision=REV
        self.archive()
    def gh(self,path):
        self.calls.append(path)
        if path=='releases/latest':return self.release
        if path.startswith('commits/'):return {'sha':self.tag_revision}
        if path.startswith('compare/'):return {'status':self.comparison}
        if path.startswith('git/commits/'):return {'tree':{'sha':self.tree}}
        raise AssertionError(path)
    def archive(self,extra=None):
        self.manifest['files']={name:{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in self.files.items()}
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w:gz') as tar:
            for name,data in {**self.files,'manifest.json':json.dumps(self.manifest).encode(),**(extra or {})}.items():
                item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o600;tar.addfile(item,io.BytesIO(data))
        self.raw=out.getvalue()
        self.release['assets']=[{'name':'minecraft-linux-arm64.tar.gz','digest':'sha256:'+hashlib.sha256(self.raw).hexdigest(),
          'browser_download_url':'https://github.com/microsoft/amplifier-acp-minecraft/releases/download/v1.0.0/minecraft-linux-arm64.tar.gz','size':len(self.raw)}]
    def run_stage(self):
        with patch('installation_native_package.target',return_value='linux-arm64'),patch('installation_native_package.urllib.request.urlopen',return_value=io.BytesIO(self.raw)):
            return stage_package(self.provider,REV,'a'*40,self.stage)
    def test_exact_published_package_stages_sdk_without_executing_it(self):
        before=(self.python.read_bytes(),self.node.read_bytes())
        result=self.run_stage();self.assertEqual(result['commit'],PIN)
        self.assertTrue((self.stage/'app/requirements.txt').is_file());self.assertTrue((self.stage/'venv/bin/python3').is_file())
        self.assertEqual(self.screens,[self.stage/'app']);self.assertFalse((self.stage/'release.tar.gz').exists())
        receipt=json.loads((self.stage/'package-receipt.json').read_text())
        self.assertEqual(receipt['package_source'],REV);self.assertEqual(receipt['revision'],REV)
        self.assertEqual((self.python.read_bytes(),self.node.read_bytes()),before)
    def test_tree_equal_reviewed_head_is_allowed(self):
        self.manifest['source_commit']='d'*40;self.archive();self.run_stage()
        self.assertIn('git/commits/'+REV,self.calls)
    def test_changed_public_bytes_fail_before_extraction(self):
        self.raw+=b'changed'
        with self.assertRaises(ContinuityError):self.run_stage()
        self.assertFalse((self.stage/'app').exists())
    def test_missing_digest_or_unapproved_download_refuses(self):
        for key,value in [('digest',''),('browser_download_url','https://example.test/other')]:
            self.archive();self.release['assets'][0][key]=value
            with self.assertRaises(ContinuityError):self.run_stage()
        self.assertFalse(self.stage.exists())
    def test_release_race_and_downgrade_are_refused(self):
        self.tag_revision='c'*40
        with self.assertRaises(ContinuityError):self.run_stage()
        self.tag_revision=REV;self.comparison='behind'
        with self.assertRaises(ContinuityError):self.run_stage()
        self.assertFalse(self.stage.exists())
    def test_wrong_target_is_refused(self):
        self.manifest['target']='windows-x64';self.archive()
        with self.assertRaisesRegex(ContinuityError,'target'):self.run_stage()
    def test_changed_base_interpreter_requires_separate_migration(self):
        self.files['python/bin/python3']=b'new interpreter';self.archive()
        with self.assertRaisesRegex(ContinuityError,'interpreter change'):self.run_stage()
        self.assertEqual(self.python.read_bytes(),b'python')
    def test_old_sdk_metadata_is_not_accepted(self):
        key=next(k for k in self.files if k.endswith('direct_url.json'))
        self.files[key]=self.files[key].replace(PIN.encode(),b'0'*40);self.archive()
        with self.assertRaisesRegex(ContinuityError,'provenance'):self.run_stage()
        self.assertFalse((self.stage/'package-receipt.json').exists())
    def test_new_shared_driver_is_not_silently_ignored(self):
        self.manifest['native_platform']['driver_sha256']='f'*64;self.archive()
        with self.assertRaisesRegex(ContinuityError,'driver change'):self.run_stage()
    def test_path_escape_refuses_without_outside_write(self):
        self.archive({'../escape':b'bad'})
        with self.assertRaisesRegex(ContinuityError,'unsafe'):self.run_stage()
        self.assertFalse((self.root/'escape').exists())
    def test_native_staging_never_falls_back_to_source_build(self):
        self.provider.c['channel']='latest-passing-development'
        with self.assertRaisesRegex(ContinuityError,'published'):self.run_stage()
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
