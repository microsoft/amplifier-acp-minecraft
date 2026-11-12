import json
import pathlib
import tempfile
import unittest
from unittest.mock import Mock

from fixture_security import protect_fixture_path,fixture_application_identities


class FixtureSecurityTests(unittest.TestCase):
    def test_delegates_permission_and_ownership_to_shared_helper_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp).resolve();target=root/'fixture';target.mkdir()
            protect=Mock()
            protect_fixture_path(target,root,protect)
            protect.assert_called_once_with(target)

    def test_outside_missing_or_indirect_path_refused_before_shared_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer=pathlib.Path(tmp).resolve();root=outer/'owned';root.mkdir();outside=outer/'other';outside.mkdir()
            protect=Mock()
            for path in (outside,root/'missing',root/'..'/'other'):
                with self.assertRaises((ValueError,FileNotFoundError)):
                    protect_fixture_path(path,root,protect)
            protect.assert_not_called()

    def test_shared_failure_stops_fixture_without_retry_or_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp).resolve();error=RuntimeError('fixture ownership refused')
            protect=Mock(side_effect=error)
            with self.assertRaises(RuntimeError) as caught:
                protect_fixture_path(root,root,protect)
            self.assertIs(caught.exception,error)
            protect.assert_called_once_with(root)

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
