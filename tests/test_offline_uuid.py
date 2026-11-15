"""An offline-route agent must be allowlisted by the UUID its server actually sees."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

from ops.offline_uuid import main, offline_uuid, whitelist_entry

NOTCH = 'b50ad385-829d-3141-a216-7e7d7539ba7f'


class OfflineUuid(unittest.TestCase):
    def test_known_java_offline_uuids(self):
        # Java: UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(UTF_8))
        for name, expected in (('Notch', NOTCH), ('jeb_', 'a762f560-4fce-3236-812a-b80efff0b62b'),
                               ('YourAgent', 'b284e613-a9ae-36f1-b7b4-5dc72f238f35')):
            self.assertEqual(offline_uuid(name), expected)

    def test_result_is_a_name_uuid_and_never_an_account_uuid(self):
        for name in ('Notch', 'YourAgent', 'a', 'Sixteen_Chars_16'):
            value = uuid.UUID(offline_uuid(name))
            self.assertEqual((value.version, value.variant), (3, uuid.RFC_4122))
            self.assertEqual(str(value), offline_uuid(name))

    def test_name_is_exact_and_case_sensitive(self):
        self.assertNotEqual(offline_uuid('notch'), NOTCH)
        self.assertNotEqual(offline_uuid('NOTCH'), NOTCH)

    def test_names_no_server_would_accept_are_refused_rather_than_hashed(self):
        for name in ('', ' Notch', 'Notch ', 'Not ch', 'Notch\n', 'x' * 17, 'Nótch', None, 7):
            with self.subTest(name=name), self.assertRaises(ValueError):
                offline_uuid(name)

    def test_whitelist_entry_is_the_servers_own_shape(self):
        self.assertEqual(whitelist_entry('Notch'), {'uuid': NOTCH, 'name': 'Notch'})

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                main(list(argv))
                code = 0
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    def test_command_prints_the_uuid_or_a_pasteable_entry(self):
        self.assertEqual(self.run_main('Notch'), (0, NOTCH + '\n', ''))
        code, out, _ = self.run_main('--whitelist-entry', 'Notch')
        self.assertEqual((code, json.loads(out)), (0, {'uuid': NOTCH, 'name': 'Notch'}))
        self.assertEqual(out.count('\n'), 1)

    def test_command_refuses_a_bad_name_without_printing_a_uuid(self):
        code, out, err = self.run_main('Not ch')
        self.assertEqual((code, out), (2, ''))
        self.assertIn('1-16 visible ASCII characters', err)

    def test_documented_invocation_needs_only_the_standard_library(self):
        script = Path(__file__).resolve().parents[1] / 'ops' / 'offline_uuid.py'
        result = subprocess.run([sys.executable, '-S', str(script), 'Notch'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, NOTCH + '\n', ''))
