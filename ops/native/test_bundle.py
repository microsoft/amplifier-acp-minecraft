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
        (self.root/'manifest.json').unlink(missing_ok=True)
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

    def test_every_validation_hashes_same_size_payload_again(self):
        self.manifest();self.launch.validate(self.root)
        path=self.root/'runtime';before=path.read_bytes();metadata=path.stat()
        path.write_bytes(b'x'*len(before))
        os.utime(path,ns=(metadata.st_atime_ns,metadata.st_mtime_ns))
        with self.assertRaisesRegex(ValueError,'Package digest changed'):
            self.launch.validate(self.root)

    def test_missing_resized_or_directory_payload_refuses(self):
        for replacement in ('missing','resized','directory'):
            with self.subTest(replacement=replacement):
                self.manifest();path=self.root/'runtime';path.unlink()
                if replacement=='resized':path.write_bytes(b'x')
                if replacement=='directory':path.mkdir()
                with self.assertRaisesRegex(ValueError,'Package file changed'):
                    self.launch.validate(self.root)
                if path.is_dir():path.rmdir()

    def symlink(self,path,target,**kwargs):
        try:path.symlink_to(target,**kwargs)
        except (OSError,NotImplementedError) as error:
            self.skipTest('Host does not permit fixture symlinks: '+str(error))

    def test_regular_payload_cannot_be_replaced_by_same_bytes_link(self):
        self.manifest();path=self.root/'runtime';data=path.read_bytes()
        (self.root/'other').write_bytes(data);path.unlink();self.symlink(path,'other')
        with self.assertRaisesRegex(ValueError,'Package file changed'):
            self.launch.validate(self.root)

    def test_exact_internal_link_and_changed_link_are_distinct(self):
        self.manifest();self.symlink(self.root/'alias','runtime')
        self.manifest();self.launch.validate(self.root)
        (self.root/'other').write_bytes((self.root/'runtime').read_bytes())
        (self.root/'alias').unlink();self.symlink(self.root/'alias','other')
        with self.assertRaisesRegex(ValueError,'Package link changed'):
            self.launch.validate(self.root)

    def test_parent_link_escape_refuses_even_with_identical_payload(self):
        nested=self.root/'nested';nested.mkdir();(nested/'payload').write_bytes(b'exact')
        self.manifest();(nested/'payload').unlink();nested.rmdir()
        with tempfile.TemporaryDirectory() as directory:
            outside=Path(directory);(outside/'payload').write_bytes(b'exact')
            self.symlink(nested,outside,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'Package path escapes'):
                self.launch.validate(self.root)

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

    def viewer_assets(self):
        public=self.root/'node_modules/prismarine-viewer/public'
        for version in ('1.16.4','1.21.1','1.21.4'):
            for name in (f'textures/{version}/entity/cow.png',f'textures/{version}.png',f'blocksStates/{version}.json'):
                p=public/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
        (public/'textures/generic.png').write_bytes(b'generic')
        return public

    def test_asset_selection_preserves_full_admitted_version_and_generic_data(self):
        public=self.viewer_assets()
        before={p.relative_to(public):p.read_bytes() for p in public.rglob('*') if p.is_file()}
        self.build.select_viewer_assets(self.root,['1.21.1'])
        after={p.relative_to(public):p.read_bytes() for p in public.rglob('*') if p.is_file()}
        self.assertEqual(after,{p:b for p,b in before.items()
            if '1.21.4' not in p.as_posix() and (not p.as_posix().startswith(('textures/1.16.4.','blocksStates/1.16.4.')))})

    def test_missing_entity_dependency_refuses_before_pruning(self):
        public=self.viewer_assets()
        import shutil
        shutil.rmtree(public/'textures/1.16.4')
        before=self.build.inventory(self.root)
        with self.assertRaisesRegex(ValueError,'Complete admitted'):
            self.build.select_viewer_assets(self.root,['1.21.1'])
        self.assertEqual(self.build.inventory(self.root),before)

    def test_missing_admitted_assets_refuses_before_pruning_other_versions(self):
        public=self.viewer_assets();(public/'textures/1.21.1.png').unlink()
        before=self.build.inventory(self.root)
        with self.assertRaisesRegex(ValueError,'Complete admitted'):
            self.build.select_viewer_assets(self.root,['1.21.1'])
        self.assertEqual(self.build.inventory(self.root),before)

    def test_runtime_layout_preserves_exact_executable_license_and_other_files(self):
        for windows in (False,True):
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                root=Path(directory);binary=root/('node.exe' if windows else 'bin/node')
                binary.parent.mkdir(parents=True,exist_ok=True);binary.write_bytes(b'exact upstream executable')
                (root/'LICENSE').write_bytes(b'upstream license');(root/'retained').write_bytes(b'other runtime data')
                for name in ('include/node/header.h','lib/node_modules/npm/cli.js','node_modules/corepack/cli.js','npm.cmd'):
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'build only')
                result=self.build.select_node_runtime(root,windows)
                self.assertTrue(result['runtime_only'])
                self.assertEqual(set(self.build.inventory(root)),{binary.relative_to(root).as_posix(),'LICENSE','retained'})
                self.assertEqual(binary.read_bytes(),b'exact upstream executable')
                self.assertEqual((root/'LICENSE').read_bytes(),b'upstream license')

    def test_javascript_layout_removes_only_declarations_and_debug_maps(self):
        keep=('index.js','index.cjs','index.mjs','source.ts','data.json','terrain.map','LICENSE','image.png')
        remove=('index.d.ts','index.d.cts','index.d.mts','index.d.ts.map','index.js.map','index.cjs.map','index.mjs.map')
        for name in (*keep,*remove):
            path=self.root/'node_modules/package'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(name.encode())
        outside=self.root/'owner.js.map';outside.write_bytes(b'not a dependency')
        before=self.build.inventory(self.root);result=self.build.select_javascript_runtime(self.root)
        after=self.build.inventory(self.root)
        self.assertEqual(after,{name:entry for name,entry in before.items() if name not in {'node_modules/package/'+n for n in remove}})
        self.assertEqual(result['removed_files'],len(remove));self.assertFalse(result['declarations_and_debug_maps_included'])
        self.assertEqual(self.build.select_javascript_runtime(self.root)['removed_files'],0)


if __name__=='__main__':unittest.main()
