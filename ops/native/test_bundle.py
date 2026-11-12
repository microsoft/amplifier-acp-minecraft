import hashlib
import importlib.util
import json
import tempfile
import sys
import os
import unittest
import zipfile
from pathlib import Path


def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.build=module('build_bundle');self.launch=module('launch')

    def manifest(self):
        (self.root/'runtime').write_bytes(b'private executable')
        data={'schema':1,'commands':{'python':'runtime','node':'runtime','task_helper':'runtime'},'files':self.build.inventory(self.root)}
        (self.root/'manifest.json').write_text(json.dumps(data));return data

    def test_windows_cli_preserves_spaced_argv_and_exit_status(self):
        script=self.root/'fixed child with spaces.py'
        script.write_text("import sys; assert sys.argv[1:] == ['home with spaces', 'literal&argument']; raise SystemExit(7)")
        self.assertEqual(self.launch.run_windows([sys.executable,str(script),'home with spaces','literal&argument'],dict(os.environ)),7)

    def test_all_six_runtime_artifacts_are_pinned(self):
        lock=json.loads(Path(__file__).with_name('runtime-lock.json').read_text())
        self.assertEqual(set(lock['targets']),{o+'-'+a for o in ('windows','macos','linux') for a in ('x64','arm64')})
        for target in lock['targets'].values():
            for entry in target.values():
                self.assertRegex(entry['sha256'],r'^[0-9a-f]{64}$');self.assertTrue(entry['url'].startswith('https://'))
        self.assertEqual(lock['sdk_commit'],'9853d8b514d6340000bcbd01ec07808436db80cf')

    def test_changed_payload_is_not_usable(self):
        self.manifest();self.launch.validate(self.root)
        (self.root/'runtime').write_bytes(b'changed executable')
        with self.assertRaises(ValueError):self.launch.validate(self.root)

    def test_manifest_cannot_redirect_command_outside_package(self):
        data=self.manifest();data['commands']['node']='../untrusted'
        (self.root/'manifest.json').write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.launch.validate(self.root)

    def test_zip_traversal_is_refused_before_extraction(self):
        for entry in ('../escape','/absolute','C:/escape','root/../../escape','root\\..\\..\\escape'):
            archive=self.root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as out:out.writestr(entry,'bad')
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                with self.assertRaises(ValueError):self.build.extract(archive,Path(directory)/'out')

    def test_changed_cached_runtime_is_not_downloaded_or_used(self):
        cached=self.root/'runtime.tar.gz';cached.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Cached'):
            self.build.fetch({'url':'https://invalid.example/runtime.tar.gz','sha256':hashlib.sha256(b'expected').hexdigest()},self.root)


if __name__=='__main__':unittest.main()
