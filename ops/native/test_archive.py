import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from test_bundle import module


class ArchiveTests(unittest.TestCase):
    def test_exact_payload_excludes_caches_and_has_reproducible_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bundle=root/'bundle';bundle.mkdir()
            binary=bundle/'binary';binary.write_bytes(b'fixed runtime');binary.chmod(0o755)
            (bundle/'unexpected-cache').write_text('not published')
            manifest={'schema':1,'target':'linux-arm64','source_commit':'a'*40,'source_clean':True,
                'commands':{k:'binary' for k in ('python','node','task_helper')},
                'files':{'binary':{'size':binary.stat().st_size,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}}}
            (bundle/'manifest.json').write_text(json.dumps(manifest))
            package=module('archive_bundle');a=package.archive(bundle,root/'first.tar.gz');b=package.archive(bundle,root/'second.tar.gz')
            self.assertEqual(a['sha256'],b['sha256'])
            with tarfile.open(root/'first.tar.gz') as tar:
                self.assertEqual(tar.getnames(),['binary','manifest.json']);self.assertTrue(tar.getmember('binary').mode&0o100)
            with self.assertRaises(ValueError):package.archive(bundle,bundle/'nested.tar.gz')
            manifest['source_clean']=False;(bundle/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'dirty'):package.archive(bundle,root/'dirty.tar.gz')

if __name__=='__main__':unittest.main()
