import json
import unittest
import sys
from pathlib import Path

from context_snapshot import META, blocks, supported


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
