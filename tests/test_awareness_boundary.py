import tempfile
import unittest

from conversation_awareness import Awareness
from harness_capabilities import INSTANCE, SOURCE_META, SOURCE_METHOD


class Client:
    info = {}
    session = 'original'
    active_prompt_id = 'active'

    def __init__(self):
        self.tool_calls = {'t': {'status': 'pending'}}
        self.calls = []

    def supports_awareness(self):
        return True

    async def request(self, method, params):
        self.calls.append((method, params))
        return {'outcome': 'injected'}


def snapshot(revision='new'):
    return {'turn_active': True, 'revision': revision, 'messages': [
        {'id': 'old', 'text': 'Old'},
        {'id': revision, 'text': 'Fresh', 'occurred_at': '2026-11-07T22:00:00Z'}]}


class ToolBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_edit_retains_original_facts_and_invalidates_old_freshness(self):
        with tempfile.TemporaryDirectory() as home:
            c = Client()
            c.info = {'_meta': {INSTANCE: {'inputContinuity': {'sourceDelivery': {
                'version': 1, 'metadata': SOURCE_META, 'receiptsMethod': SOURCE_METHOD}}}}}
            original = snapshot()
            original['messages'][-1]['source_fact'] = {'id': 'new', 'revision': 'v1', 'occurredAt': 123456}
            a = Awareness(home, c, original, lambda *a, **kw: None)
            edited = snapshot()
            edited['messages'][-1]['source_fact'] = {'id': 'new', 'revision': 'v2', 'occurredAt': 123456}
            await a.consider(edited)
            self.assertEqual(c.calls, [])
            self.assertEqual(a.source_revisions, {'new': 'v1'})
            self.assertEqual(a.receipts, [])
            self.assertIsNone(a.final_revision({**edited, 'exposed_revision': 'new'}))
            c.tool_calls['t']['status'] = 'completed'
            await a.consider(edited)
            self.assertEqual(c.calls[0][1]['_meta'][SOURCE_META]['sources'],
                             [{'id': 'new', 'revision': 'v2', 'occurredAt': 123456}])

    async def test_pending_tool_preserves_source_then_delivers_once_after_settlement(self):
        for audience in ('public', 'operator'):
            for terminal in ('completed', 'failed'):
                with self.subTest(audience=audience, terminal=terminal), tempfile.TemporaryDirectory() as home:
                    c = Client()
                    events = []
                    a = Awareness(home, c, {'revision': 'old'}, lambda kind, **kw: events.append(kind), audience=audience)
                    before = a.path.read_bytes()
                    for status in ('pending', 'in_progress', None):
                        c.tool_calls['t']['status'] = status
                        await a.consider(snapshot())
                    self.assertEqual(c.calls, [])
                    self.assertEqual(a.cursor, 'old')
                    self.assertEqual(a.receipts, [])
                    self.assertEqual(a.path.read_bytes(), before)
                    self.assertEqual(events.count('awareness_deferred'), 1)
                    c.tool_calls['t']['status'] = terminal
                    await a.consider(snapshot())
                    await a.consider(snapshot())
                    self.assertEqual(len(c.calls), 1)
                    self.assertEqual(a.cursor, 'new')
                    self.assertEqual(a.receipts[0]['state'], 'received')
                    self.assertIn('2026-11-07T22:00:00Z', c.calls[0][1]['prompt'][0]['text'])

    async def test_prompt_ending_during_tool_wait_does_not_start_or_replay_prompt(self):
        with tempfile.TemporaryDirectory() as home:
            c = Client()
            a = Awareness(home, c, {'revision': 'old'}, lambda *a, **kw: None)
            await a.consider(snapshot())
            c.active_prompt_id = None
            await a.consider({**snapshot(), 'turn_active': False})
            self.assertEqual(c.calls, [])
            self.assertEqual(a.receipts[0]['reason'], 'no_active_turn')
            self.assertEqual(a.receipts[0]['state'], 'history_only')

    async def test_newer_evidence_coalesces_without_claiming_deferred_source_delivery(self):
        with tempfile.TemporaryDirectory() as home:
            c = Client()
            a = Awareness(home, c, {'revision': 'old'}, lambda *a, **kw: None)
            await a.consider(snapshot())
            newer = snapshot('later')
            newer['messages'].insert(1, snapshot()['messages'][1])
            await a.consider(newer)
            self.assertEqual(c.calls, [])
            c.tool_calls.clear()
            await a.consider(newer)
            self.assertEqual(len(c.calls), 1)
            self.assertEqual(a.receipts[0]['source_ids'], ['new', 'later'])
            self.assertEqual(a.receipts[0]['state'], 'received')

    async def test_tool_context_exposure_needs_no_steering_even_while_tool_pending(self):
        with tempfile.TemporaryDirectory() as home:
            c = Client()
            a = Awareness(home, c, {'revision': 'old'}, lambda *a, **kw: None)
            await a.consider({**snapshot(), 'exposed_revision': 'new'})
            self.assertEqual(c.calls, [])
            self.assertEqual(a.receipts[0]['reason'], 'already_supplied_by_tool')
