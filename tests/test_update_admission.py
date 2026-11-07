import os
import tempfile
import unittest
from pathlib import Path
from installation_guard import ContinuityError, durable_write, read
from update_admission import held, process_identity


class AdmissionTests(unittest.TestCase):
    def test_acknowledgment_binds_transaction_and_real_process_without_game_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);durable_write(home/'workshop.json',{'task':'keep','unknown':['keep']})
            before=(home/'workshop.json').read_bytes()
            self.assertFalse(held(home,acknowledge=True))
            durable_write(home/'installation-updates/gate.json',{'version':1,'transaction_id':'one','closed':True})
            self.assertTrue(held(home,acknowledge=True))
            self.assertEqual(read(home/'installation-updates/controller-idle.json'),{'transaction_id':'one',**process_identity(os.getpid())})
            self.assertEqual((home/'workshop.json').read_bytes(),before)
            durable_write(home/'installation-updates/gate.json',{'version':1,'transaction_id':'two','closed':True})
            held(home,acknowledge=True)
            self.assertEqual(read(home/'installation-updates/controller-idle.json')['transaction_id'],'two')
    def test_malformed_gate_never_acknowledges_or_implies_open(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);durable_write(home/'installation-updates/gate.json',{})
            with self.assertRaises(ContinuityError):held(home,acknowledge=True)
            self.assertFalse((home/'installation-updates/controller-idle.json').exists())
