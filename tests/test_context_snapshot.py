import copy
import json
import unittest
import sys
from pathlib import Path

from context_snapshot import META, blocks, retained_request, supported


class ContextSnapshot(unittest.TestCase):
    def info(self):
        return {'_meta': {META: {'version': 1, 'contentBlocks': True,
                               'originalHistoryPreserved': True}}}

    def test_plain_and_partial_acp_keep_original_prompt_without_extensions(self):
        for info in ({}, {'_meta': None}, {'_meta': {META: {'version': 1}}},
                     {'_meta': {META: {'version': True, 'contentBlocks': True,
                                      'originalHistoryPreserved': True}}}):
            self.assertFalse(supported(info))
            self.assertEqual(blocks(info, 'POLICY', 'WORLD', 'REQUEST', 'install', 'rev'),
                             [{'type': 'text', 'text': 'POLICY'}, {'type': 'text', 'text': 'WORLD'}])

    def test_original_correction_and_expired_bounds_survive_projection(self):
        messages = [{'id': 'human-7', 'source': 'human', 'message': 'Stop crafting. Keep the log.',
                     'source_fact': {'revision': 'r2', 'occurredAt': '2026-11-07T00:00:00Z'}}]
        world = {'task': {'id': 'same', 'request': 'Collect a log', 'status': 'budget_exhausted',
                         'turns': 8, 'max_turns': 7, 'deadline': 123, 'authority_revision': 2,
                         'progress': [{'observation': 'very large old observation'}]}}
        originals = copy.deepcopy((messages, world))
        retained = retained_request(messages, world)
        value = json.loads(retained.split('\n', 1)[1])
        self.assertEqual(value['messages'], messages)
        self.assertEqual(value['historical_assignment']['max_turns'], 7)
        self.assertEqual(value['historical_assignment']['turns'], 8)
        self.assertEqual(value['historical_assignment']['deadline'], 123)
        self.assertNotIn('progress', value['historical_assignment'])
        self.assertEqual((messages, world), originals)
        p = blocks(self.info(), 'POLICY', 'WHOLE ORIGINAL WORLD', retained, 'install', 'rev')
        self.assertEqual(p[1]['text'], 'WHOLE ORIGINAL WORLD')
        self.assertEqual(p[1]['_meta'][META]['retainedText'], retained)
        self.assertNotEqual(p[0]['_meta'][META]['key'], p[1]['_meta'][META]['key'])

    def test_large_unicode_request_is_not_partially_retained(self):
        messages = [{'message': '\U0001f333' * 10000}]
        retained = retained_request(messages, {})
        self.assertIsNone(retained)
        p = blocks(self.info(), 'POLICY', 'COMPLETE REQUEST', retained, 'install', 'rev')
        self.assertNotIn('_meta', p[1])
        self.assertEqual(p[1]['text'], 'COMPLETE REQUEST')

    def test_installations_have_distinct_projection_keys(self):
        a = blocks(self.info(), 'P', 'W', 'R', 'one', 'rev')
        b = blocks(self.info(), 'P', 'W', 'R', 'two', 'rev')
        self.assertNotEqual(a[1]['_meta'][META]['key'], b[1]['_meta'][META]['key'])


class SnapshotWire(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_preserves_optional_metadata_and_vanilla_fallback(self):
        from acp_client import Client
        for advertised in (False, True):
            command = [sys.executable, str(Path(__file__).with_name('sdk_agent_fixture.py'))]
            if advertised:
                command.append('snapshots')
            c = Client({'command': command, 'cwd': '/tmp'}, lambda *a, **k: None)
            try:
                await c.start()
                await c.open_session()
                result = await c.prompt('snapshot-wire', timeout=3, snapshot_retained='Exact human request', snapshot_key='one-install')
                parts = json.loads(result['final_text'])
                self.assertEqual(parts[-1]['text'], 'snapshot-wire')
                self.assertEqual('_meta' in parts[-1], advertised)
                if advertised:
                    self.assertEqual(parts[-1]['_meta'][META]['retainedText'], 'Exact human request')
            finally:
                await c.close()
