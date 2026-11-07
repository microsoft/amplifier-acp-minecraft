import copy
import json
import tempfile
import unittest
from pathlib import Path

from installation_guard import (ContinuityError, NotIdle, Receipt, continuity,
                                installation_lock, require_idle, restore_plan, snapshot)


class InstallationGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.history = {'task': {'id': 'same-task', 'turns': 8, 'max_turns': 7,
                                  'status': 'budget_exhausted'}, 'turn': None,
                        'events': [], 'unknown_receipts': ['unknown-do-not-replay'],
                        'action_sequences': [], 'future_authority': {'revision': 2}}
        self.write()
        (self.home/'session.json').write_text('{"session_id":"original"}')
        self.services = {kind: {'ActiveState': 'active', 'MainPID': str(pid),
                               'ExecMainStartTimestamp': 'original', 'LoadState': 'loaded',
                               'UnitFileState': 'enabled', 'unit_sha256': 'unit'}
                         for kind, pid in [('body', 100), ('controller', 101)]}
        self.body = {'ready': True, 'busy': False, 'turn_active': False,
                     'task': self.history['task'], 'inventory': [{'name': 'stone', 'count': 3}],
                     'position': {'x': 1, 'y': 62, 'z': 3},
                     'action_lease': {'version': 1, 'lease_id': None, 'expires_at': 0, 'renewable': False}}

    def write(self):
        (self.home/'workshop.json').write_text(json.dumps(self.history))

    def snap(self):
        status = {**self.body, 'action_sequence': None}
        return snapshot(self.home, copy.deepcopy(self.services), copy.deepcopy(self.body), status)

    def test_settled_expired_task_and_unknown_history_are_preserved(self):
        before = self.snap()
        require_idle(before)
        self.assertTrue(all(continuity(before, self.snap()).values()))
        self.assertEqual(json.loads((self.home/'workshop.json').read_text()), self.history)

    def test_every_busy_or_unknown_boundary_defers(self):
        original = self.snap()
        mutations = [lambda v: v.update(turn={'id': 'work'}),
                     lambda v: v.update(sequence_states=['running']),
                     lambda v: v.update(sequence={'status': 'running'}),
                     lambda v: v.update(status_observed=False),
                     lambda v: v.update(status_idle=False),
                     lambda v: v['body'].update(busy=True),
                     lambda v: v['body'].update(turn_active=True),
                     lambda v: v['body'].update(ready=False),
                     lambda v: v['body'].update(inventory=None),
                     lambda v: v['body'].update(action_lease={}),
                     lambda v: v['body']['action_lease'].update(lease_id='active'),
                     lambda v: v['body']['action_lease'].update(expires_at=1),
                     lambda v: v['services']['controller'].update(ActiveState='deactivating'),
                     lambda v: v['services']['body'].update(MainPID='0')]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            with self.assertRaises(NotIdle):
                require_idle(value)

    def test_status_missing_operation_field_is_not_idle(self):
        value = snapshot(self.home, self.services, self.body, self.body)
        with self.assertRaises(NotIdle):
            require_idle(value)

    def test_pending_input_and_new_authority_fields_are_not_discarded(self):
        before = self.snap()
        for key, value in [('future_authority', {'revision': 3}),
                           ('unknown_receipts', [])]:
            previous = copy.deepcopy(self.history)
            self.history[key] = value
            self.write()
            with self.assertRaises(ContinuityError):
                continuity(before, self.snap())
            self.history = previous
            self.write()

    def test_new_incoming_observations_retained_but_old_input_cannot_be_removed(self):
        self.history['inbox']=[{'id':'already-pending','source':'human'}];self.write()
        before=self.snap()
        self.history['inbox'].append({'id':'arrived','source':'human'})
        self.history['activity_tracks']={'human':{'revision':'new-observation'}};self.write()
        continuity(before,self.snap())
        self.history['inbox'].pop(0);self.write()
        with self.assertRaises(ContinuityError):continuity(before,self.snap())

    def test_rolling_events_can_arrive_without_authority_rollback(self):
        before = self.snap()
        self.history['events'].append({'type': 'chat', 'text': 'arrived during update'})
        self.write()
        continuity(before, self.snap())
        self.assertEqual(len(json.loads((self.home/'workshop.json').read_text())['events']), 1)

    def test_new_or_changed_accounting_file_is_detected(self):
        before = self.snap()
        (self.home/'new-accounting.json').write_text('{}')
        with self.assertRaises(ContinuityError):
            continuity(before, self.snap())

    def test_symlinked_receipt_directory_rejected(self):
        (self.home/'maintenance-receipts').symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(ContinuityError):
            self.snap()

    def test_inventory_position_and_shared_body_pid_must_match(self):
        before = self.snap()
        for key in ('inventory', 'position'):
            after = copy.deepcopy(before)
            after['body'][key] = []
            with self.assertRaises(ContinuityError):
                continuity(before, after)
        after = copy.deepcopy(before)
        after['services']['body']['MainPID'] = '200'
        with self.assertRaises(ContinuityError):
            continuity(before, after)
        continuity(before, after, body_restart=True)

    def test_stopped_installation_remains_stopped(self):
        for service in self.services.values():
            service.update(ActiveState='inactive', MainPID='0', LoadState='masked', UnitFileState='masked')
        require_idle(snapshot(self.home, self.services))
        self.assertEqual(restore_plan(self.services, self.services),
                         {'body': 'leave_stopped', 'controller': 'leave_stopped'})

    def test_external_mask_or_unit_change_blocks_restore(self):
        for change in [{'LoadState': 'masked'}, {'UnitFileState': 'disabled'}, {'unit_sha256': 'new'}]:
            current = copy.deepcopy(self.services)
            current['controller'].update(change)
            with self.assertRaises(ContinuityError):
                restore_plan(self.services, current)

    def test_restore_preserves_independent_service_intentions(self):
        self.services['controller'].update(ActiveState='inactive', MainPID='0')
        self.assertEqual(restore_plan(self.services, self.services),
                         {'body': 'start', 'controller': 'leave_stopped'})

    def test_lost_reply_reopens_receipt_without_repeating_operation(self):
        path = self.home/'update-receipt'
        first = Receipt(path, 'txn', {'component': 'minecraft'})
        stale = Receipt(path, 'txn', {'component': 'minecraft'})
        first.transition({'new'}, 'applying', preserved_task='same-task')
        with self.assertRaises(ContinuityError):
            stale.transition({'new'}, 'applying')
        recovered = Receipt(path, 'txn', {'component': 'minecraft'})
        self.assertEqual(recovered.value['state'], 'applying')
        with self.assertRaises(ContinuityError):
            recovered.transition({'new'}, 'applying')
        with self.assertRaises(ContinuityError):
            Receipt(path, 'txn', {'component': 'different'})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_installation_lock_excludes_other_provider_or_participant(self):
        path = self.home/'installation.lock'
        with installation_lock(path):
            with self.assertRaises(NotIdle):
                with installation_lock(path):
                    self.fail('second operation admitted')
        with installation_lock(path):
            pass


if __name__ == '__main__':
    unittest.main()
