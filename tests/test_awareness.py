import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from acp_client import Client
from conversation_awareness import Awareness

FIXTURE = Path(__file__).with_name('steering_fixture.py')


def snapshot(revision='new'):
    return {'turn_active': True, 'revision': revision, 'messages': [
        {'id': 'old', 'author': 'Lead', 'text': 'Please deliver sticks.'},
        {'id': revision, 'author': 'Peer', 'text': 'Sticks are already in the chest.'}]}


class AwarenessWire(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, mode):
        observed = []
        c = Client({'command': [sys.executable, str(FIXTURE), mode], 'cwd': '/tmp'},
                   lambda kind, **data: observed.append((kind, data)))
        try:
            await c.start()
            await c.open_session()
            c.permission_active = lambda: True
            with tempfile.TemporaryDirectory() as tmp:
                awareness = Awareness(tmp, c, {'revision': 'old'}, c.observe)
                task = asyncio.create_task(c.prompt('Existing accepted work', 10))
                while c.active_prompt_id is None:
                    await asyncio.sleep(.001)
                prompt_id = c.active_prompt_id
                await awareness.consider(snapshot())
                result = await task
                self.assertEqual(result['final_text'], 'Fresh peer evidence received.')
                self.assertEqual(result['unsettled_tools'], [])
                self.assertIsNone(c.active_prompt_id)
                self.assertEqual(len(awareness.sent), 1)
                self.assertEqual(awareness.sent[0]['prompt_id'], prompt_id)
                self.assertEqual(awareness.sent[0]['state'], 'unknown' if mode == 'lost' else 'received')
                self.assertIsNone(awareness.final_revision(snapshot()))
                await awareness.finish()
                self.assertEqual(awareness.final_revision(snapshot()), 'new')
                self.assertEqual(awareness.sent[0]['state'], 'incorporated')
                self.assertEqual(sum(kind == 'game_permission_allowed' for kind, _ in observed), 1)
                # Re-observation and restart do not turn a delivery journal into a replay queue.
                await awareness.consider(snapshot())
                other = Awareness(tmp, c, {'revision': 'old'}, c.observe)
                await other.consider(snapshot())
                self.assertEqual(other.sent, [])
                await other.consider(snapshot('late'))
                self.assertEqual(other.receipts[-1]['state'], 'history_only')
                self.assertEqual(other.receipts[-1]['reason'], 'no_active_turn')
                self.assertEqual(c.session, 'saved-agent')
        finally:
            await c.close()

    async def test_advertised_native_receipts_reconcile_delivery(self):
        await self.exercise('native')

    async def test_steering_without_receipt_capability_never_queries_or_claims_incorporation(self):
        observed = []
        c = Client({'command': [sys.executable, str(FIXTURE), 'codex'], 'cwd': '/tmp'},
                   lambda kind, **data: observed.append((kind, data)))
        try:
            await c.start(); await c.open_session()
            c.permission_active = lambda: True
            with tempfile.TemporaryDirectory() as tmp:
                a = Awareness(tmp, c, {'revision': 'old'}, c.observe)
                task = asyncio.create_task(c.prompt('Existing accepted work', 10))
                while c.active_prompt_id is None:
                    await asyncio.sleep(.001)
                await a.consider(snapshot())
                result = await task
                self.assertEqual(result['final_text'], 'Fresh peer evidence received.')
                before = c.requests_sent
                await a.finish()
                self.assertEqual(c.requests_sent, before, 'Do not probe an unadvertised native extension')
                self.assertEqual(a.sent[0]['state'], 'received')
                self.assertIsNone(a.final_revision(snapshot()))
                self.assertIn(('awareness_receipt_unavailable', {'category': 'unsupported'}), observed)
                self.assertFalse(any(kind == 'awareness_receipt' for kind, _ in observed))
                # Unknown incorporation is not a license to replay the update.
                other = Awareness(tmp, c, {'revision': 'old'}, c.observe)
                await other.consider(snapshot())
                self.assertEqual(other.sent, [])
                self.assertEqual(other.receipts[-1]['state'], 'received')
                self.assertEqual(c.requests_sent, before)
        finally:
            await c.close()

    async def test_lost_steering_response_is_unknown_then_queryable_without_replay(self):
        await self.exercise('lost')

    async def test_late_awareness_cannot_start_a_new_prompt(self):
        c = Client({'command': [sys.executable, str(FIXTURE), 'native'], 'cwd': '/tmp'}, lambda *a, **k: None)
        try:
            await c.start(); await c.open_session()
            result = await c.request('_session/steering', {'sessionId': c.session, 'prompt': [{'type': 'text', 'text': 'Late'}],
                '_meta': {'steering': {'inputId': 'late', 'idleBehavior': 'promptRequired', 'intent': 'awareness', 'activePromptId': 999}}})
            self.assertEqual(result['outcome'], 'promptRequired')
            self.assertIsNone(c.active_prompt_id)
        finally:
            await c.close()

    async def test_generic_acp_falls_back_to_context_without_optional_requests(self):
        c = Client({}, lambda *a, **k: None)
        c.info = {'_meta': {'steering': {'supported': True}}}  # Missing active-only binding.
        c.session, c.active_prompt_id = 'generic', 7
        with tempfile.TemporaryDirectory() as tmp:
            a = Awareness(tmp, c, {'revision': 'old'}, c.observe)
            await a.consider(snapshot()); await a.finish()
            self.assertEqual(a.receipts[-1]['reason'], 'unsupported')
            self.assertIsNone(a.final_revision(snapshot()))
            self.assertEqual(a.final_revision({**snapshot(), 'exposed_revision': 'new'}), 'new')
            self.assertEqual(c.requests_sent, 0)

    async def test_crash_journal_and_delivery_limit_do_not_request_more_work(self):
        class Fake:
            session = 's'
            active_prompt_id = 3
            def supports_awareness(self): return True
            async def request(self, method, params): raise AssertionError('Must not send')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'awareness-receipts.json'
            p.write_text(json.dumps([{'input_id': 'interrupted', 'state': 'sending'}]))
            a = Awareness(tmp, Fake(), {'revision': 'old'}, lambda *a, **k: None, limit=0)
            self.assertEqual(a.receipts[0]['state'], 'unknown')
            await a.consider(snapshot())
            self.assertEqual(a.receipts[-1]['reason'], 'turn_delivery_limit')
            self.assertEqual(a.sent, [])
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    async def test_corrupt_receipt_file_is_preserved_and_does_not_block_normal_tool_context(self):
        c = Client({}, lambda *a, **k: None); c.session = 'saved'; c.active_prompt_id = 5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'awareness-receipts.json'; path.write_text('incomplete journal')
            a = Awareness(tmp, c, {'revision': 'old'}, c.observe)
            await a.consider(snapshot())
            self.assertEqual(a.receipts[-1]['reason'], 'journal_unavailable')
            self.assertEqual(path.read_text(), 'incomplete journal')
            self.assertEqual(c.requests_sent, 0)

    async def test_context_already_supplied_by_a_tool_is_not_injected_again(self):
        class Fake:
            session = 's'
            active_prompt_id = 3
            def supports_awareness(self): return True
            async def request(self, method, params): raise AssertionError('Duplicate evidence must not be sent')
        with tempfile.TemporaryDirectory() as tmp:
            a = Awareness(tmp, Fake(), {'revision': 'old'}, lambda *a, **k: None)
            await a.consider({**snapshot(), 'exposed_revision': 'new'})
            self.assertEqual(a.receipts[-1]['reason'], 'already_supplied_by_tool')
            self.assertEqual(a.sent, [])

    async def test_journal_write_failure_keeps_tool_fallback_without_sending(self):
        class Fake:
            session = 's'
            active_prompt_id = 3
            def supports_awareness(self): return True
            async def request(self, method, params): raise AssertionError('Unjournaled input must not be sent')
        with tempfile.TemporaryDirectory() as tmp:
            a = Awareness(tmp, Fake(), {'revision': 'old'}, lambda *a, **k: None)
            with patch.object(Path, 'replace', side_effect=OSError('Full filesystem')):
                await a.consider(snapshot())
            self.assertEqual(a.sent, [])
            self.assertEqual(a.receipts[-1]['reason'], 'journal_unavailable')
            self.assertEqual(a.final_revision({**snapshot(), 'exposed_revision': 'new'}), 'new')

    def test_malformed_optional_capability_is_unsupported(self):
        c = Client({}, lambda *a, **k: None)
        for value in (None, [], {'_meta': None}, {'_meta': {'io.github.bkrabach.agent-instance': []}},
                      {'_meta': {'steering': True}}, {'_meta': {'io.github.bkrabach.agent-instance': {'inputContinuity': {'awareness': True}}}}):
            c.info = value
            self.assertFalse(c.supports_awareness())

    def test_receipt_queries_require_their_own_advertised_capability(self):
        c = Client({}, lambda *a, **k: None)
        for value in (None, [], {'_meta': None}, {'_meta': {'steering': True}},
                      {'_meta': {'steering': {'supported': True}}},
                      {'_meta': {'steering': {'supported': False, 'receiptsMethod': '_session/input_receipts'}}},
                      {'_meta': {'steering': {'supported': True, 'receiptsMethod': '_session/unknown'}}}):
            c.info = value
            self.assertFalse(c.supports_input_receipts())
        c.info = {'_meta': {'steering': {'supported': True, 'receiptsMethod': '_session/input_receipts'}}}
        self.assertTrue(c.supports_input_receipts())

class OperatorAwareness(unittest.IsolatedAsyncioTestCase):
    async def test_operator_delivery_is_private_separate_and_never_replayed(self):
        class Fake:
            info={}
            session='same-session'
            active_prompt_id='active'
            calls=[]
            def supports_awareness(self): return True
            async def request(self,method,params):
                self.calls.append((method,params))
                return {'outcome':'injected'}
        with tempfile.TemporaryDirectory() as home:
            client=Fake();observe=lambda *a,**k:None
            public=Awareness(home,client,{'revision':'empty'},observe)
            operator=Awareness(home,client,{'revision':'empty'},observe,audience='operator')
            update={'revision':'owner-1','turn_active':True,'messages':[{'id':'owner-1','author':'Operator','text':'Keep the lamp.'}]}
            await operator.consider(update);await operator.consider(update)
            self.assertEqual(len(client.calls),1)
            text=client.calls[0][1]['prompt'][0]['text']
            self.assertIn('private control-channel',text);self.assertNotIn('Public Minecraft conversation',text)
            self.assertEqual(public.receipts,[])
            self.assertNotEqual(public.path,operator.path)
            self.assertEqual(operator.receipts[0]['state'],'received','acceptance is not incorporation')
            restarted=Awareness(home,client,{'revision':'empty'},observe,audience='operator')
            await restarted.consider(update)
            self.assertEqual(len(client.calls),1)
