import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from package_overlay import PREFIXES, overlay


class OverlayTests(unittest.TestCase):
    def test_minimal_overlay_preserves_dependencies_and_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); base = root/'base.jar'; built = root/'built.jar'; output = root/'result.jar'
            with zipfile.ZipFile(base, 'w') as z:
                z.writestr('unrelated/Dependency.class', b'original dependency')
                z.writestr('config.yml', b'original defaults')
                z.writestr(PREFIXES[0]+'.class', b'old code')
            with zipfile.ZipFile(built, 'w') as z:
                for name in PREFIXES:
                    z.writestr(name+'.class', b'reviewed patch')
                z.writestr('unrelated/Dependency.class', b'unintended snapshot upgrade')
            receipt = overlay(base, built, output, hashlib.sha256(base.read_bytes()).hexdigest())
            with zipfile.ZipFile(output) as z:
                self.assertEqual(z.read('unrelated/Dependency.class'), b'original dependency')
                self.assertEqual(z.read('config.yml'), b'original defaults')
                self.assertEqual(z.read(PREFIXES[0]+'.class'), b'reviewed patch')
            self.assertTrue(receipt['all_other_original_entries_byte_exact'])
            with self.assertRaises(ValueError):
                overlay(base, built, output, hashlib.sha256(base.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                overlay(base, built, root/'unknown.jar', '0'*64)
            self.assertFalse((root/'unknown.jar').exists())

    def test_missing_classes_reject_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); base = root/'base.jar'; built = root/'built.jar'
            for path in (base, built):
                with zipfile.ZipFile(path, 'w') as z:
                    z.writestr('other', b'content')
            with self.assertRaises(ValueError):
                overlay(base, built, root/'output.jar', hashlib.sha256(base.read_bytes()).hexdigest())
            self.assertFalse((root/'output.jar').exists())


if __name__ == '__main__':
    unittest.main()
