import copy
import unittest
from task_bounds import allowance_remaining

class BoundTests(unittest.TestCase):
    def task(self):
        return {'turns': 8, 'bounds': {'version': 1, 'deadline_ms': {'kind': 'no_configured_bound'}, 'max_turns': {'kind': 'no_configured_bound'}}}

    def test_completion_bound_has_no_sentinel_and_finite_dimensions_still_restrict(self):
        task = self.task()
        self.assertTrue(allowance_remaining(task, 10**15))
        for key, field, value in [('max_turns', 'max_turns', 8), ('deadline_ms', 'deadline', 1000)]:
            changed = copy.deepcopy(task)
            changed['bounds'][key] = {'kind': 'finite', 'value': value}
            changed[field] = value
            self.assertFalse(allowance_remaining(changed, 1000))
            changed['bounds'][key]['value'] += 1
            changed[field] += 1
            self.assertTrue(allowance_remaining(changed, 1000))

    def test_missing_null_unknown_contradictory_and_boolean_values_never_mean_unlimited(self):
        for value in [None, {}, {'kind': 'unknown'}, {'kind': 'no_configured_bound', 'value': 9}, {'kind': 'finite', 'value': True}]:
            task = self.task()
            task['bounds']['deadline_ms'] = value
            self.assertFalse(allowance_remaining(task, 1000))
        for field, value in [('bounds', None), ('deadline', None), ('max_turns', 999), ('turns', True)]:
            task = self.task()
            task[field] = value
            self.assertFalse(allowance_remaining(task, 1000))
        task = self.task()
        task['bounds']['version'] = True
        self.assertFalse(allowance_remaining(task, 1000))
        self.assertFalse(allowance_remaining({'turns': 0}, 1000))

    def test_legacy_finite_records_are_not_converted_or_renewed(self):
        task = {'turns': 8, 'max_turns': 12, 'deadline': 2000}
        original = copy.deepcopy(task)
        self.assertTrue(allowance_remaining(task, 1000))
        self.assertFalse(allowance_remaining(task, 2000))
        self.assertEqual(task, original)
