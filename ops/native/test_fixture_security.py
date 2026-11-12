import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from fixture_security import protect_fixture_path,fixture_application_identities


class FixtureSecurityTests(unittest.TestCase):
    def test_windows_sets_only_current_owner_after_shared_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp).resolve();target=root/'fixture';target.mkdir()
            calls=[]
            def protect(path):calls.append(('protect',path))
            def run(argv,**kwargs):calls.append(('owner',argv,kwargs))
            protect_fixture_path(target,root,protect,windows=True,user_sid='S-1-5-21-123',run=run)
            self.assertEqual(calls[0],('protect',target))
            self.assertEqual(calls[1][1],['icacls.exe',str(target),'/setowner','*S-1-5-21-123','/L','/Q'])
            self.assertEqual(calls[1][2],{'capture_output':True,'text':True,'timeout':10,'check':True})

    def test_posix_uses_shared_protection_without_windows_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp).resolve();protect=Mock();run=Mock()
            protect_fixture_path(root,root,protect,run=run)
            protect.assert_called_once_with(root);run.assert_not_called()

    def test_outside_path_and_bad_sid_are_refused_before_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer=pathlib.Path(tmp).resolve();root=outer/'owned';root.mkdir();outside=outer/'other';outside.mkdir()
            protect=Mock();run=Mock()
            for path,sid in [(outside,'S-1-5-21-123'),(root,'Everyone'),(root,None),(root,'S-1-5;whoami')]:
                with self.assertRaises(ValueError):
                    protect_fixture_path(path,root,protect,windows=True,user_sid=sid,run=run)
            protect.assert_not_called();run.assert_not_called()

    def test_owner_failure_stops_fixture_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp).resolve();run=Mock(side_effect=subprocess.CalledProcessError(1,['icacls.exe']))
            with self.assertRaises(subprocess.CalledProcessError):
                protect_fixture_path(root,root,Mock(),windows=True,user_sid='S-1-5-21-123',run=run)
            self.assertEqual(run.call_count,1)

    def test_cleanup_preserves_actual_body_and_controller_receipt_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=pathlib.Path(tmp)/'identity.json'
            self.assertEqual(fixture_application_identities(receipt,'body'),[])
            for role in ('body','controller'):
                value={'schema':1,'service':role,'supervisor':{'pid':10,'birth':'original'},'application':{'pid':11,'birth':'original'}}
                receipt.write_text(json.dumps(value));before=receipt.read_bytes()
                self.assertEqual(fixture_application_identities(receipt,role),[value['supervisor'],value['application']])
                with self.assertRaises(ValueError):
                    fixture_application_identities(receipt,'controller' if role=='body' else 'body')
                self.assertEqual(receipt.read_bytes(),before)
            with self.assertRaises(ValueError):fixture_application_identities(receipt,'unrelated')


if __name__=='__main__':unittest.main()
