"""Negotiated no-forward facts, across actual official SDK error transport."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from acp_client import Client, ProtocolError

META = 'com.microsoft.amplifier.attention'
OFFER = {'id': 'original-offer', 'ticket': 'never-log-ticket'}


class AttentionRejection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.client = Client({'command': [sys.executable, str(Path(__file__).with_name('attention_rejection_fixture.py'))],
                              'cwd': str(Path(__file__).parent.resolve())},
                             lambda kind, **data: self.events.append((kind, data)))
        await self.client.start()
        await self.client.open_session()

    async def asyncTearDown(self):
        await self.client.close()

    async def rejection(self, mode='valid', offer=OFFER):
        before = self.client.requests_sent
        with self.assertRaises(ProtocolError) as caught:
            await self.client.prompt(mode, timeout=3, attention_offer=offer)
        self.assertEqual(self.client.requests_sent, before + 1)
        self.assertIsNone(self.client.active_prompt_id)
        self.assertNotIn('never-log', str(caught.exception))
        self.assertNotIn('never-log', json.dumps(self.events))
        return caught.exception

    async def test_correlated_sdk_data_is_retained_without_replay_or_settlement(self):
        error = await self.rejection()
        self.assertEqual(error.no_forward_receipt, {
            'version': 1, 'id': 'original-offer', 'sessionId': 'original-session',
            'outcome': 'not_forwarded'})
        events = [v for k, v in self.events if k == 'attention_not_forwarded']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['offer_id'], 'original-offer')
        self.assertEqual(events[0]['session_id'], 'original-session')
        self.assertIs(events[0]['effects_settled'], False)
        self.assertEqual(self.client.session, 'original-session')
        self.assertFalse(self.client.transport_closed())
        # A separately submitted fresh request works; the rejected one is never retried.
        before = self.client.requests_sent
        self.assertEqual((await self.client.prompt('independent', timeout=3))['stop_reason'], 'end_turn')
        self.assertEqual(self.client.requests_sent, before + 1)

    async def test_error_code_alone_does_not_choose_delivery_outcome(self):
        self.assertEqual((await self.rejection('other-code')).no_forward_receipt['outcome'], 'not_forwarded')
        error = await self.rejection('missing')
        self.assertEqual(error.request_error_code, -32002)
        self.assertIsNone(getattr(error, 'no_forward_receipt', None))

    async def test_absent_unknown_and_malformed_capability_remain_unknown(self):
        original = deepcopy(self.client.info)
        variants = [None, [], {}, {'version': True}, {'version': 2},
                    {'noForwardRejectionVersion': None}, {'noForwardRejectionVersion': 2},
                    {'noForwardRejectionVersion': True}, {'noForwardRejectionVersion': 1.0},
                    {'promptMetadata': 'another-namespace'}]
        for change in variants:
            with self.subTest(change=change):
                self.client.info = deepcopy(original)
                cap = self.client.info['_meta'][META]
                if isinstance(change, dict) and change:
                    cap.update(change)
                else:
                    self.client.info['_meta'][META] = change
                error = await self.rejection()
                self.assertIsNone(getattr(error, 'no_forward_receipt', None))
        self.assertFalse(any(k == 'attention_not_forwarded' for k, _ in self.events))

    async def test_mismatched_malformed_and_unrelated_evidence_remains_unknown(self):
        for mode in ('wrong-offer', 'wrong-session', 'future-version', 'bool-version',
                     'float-version', 'wrong-outcome', 'missing', 'wrong-type', 'unrelated-response'):
            with self.subTest(mode=mode):
                self.assertIsNone(getattr(await self.rejection(mode), 'no_forward_receipt', None))
        self.assertFalse(any(k == 'attention_not_forwarded' for k, _ in self.events))

    async def test_original_request_ids_must_be_bounded_and_nonempty(self):
        for offer in (None, {}, {'id': ''}, {'id': 7}, {'id': 'x' * 513}, {'id': 'é' * 257}):
            with self.subTest(offer=offer):
                self.assertIsNone(getattr(await self.rejection(offer=offer), 'no_forward_receipt', None))
        self.assertFalse(any(k == 'attention_not_forwarded' for k, _ in self.events))

    async def test_steering_rejection_does_not_settle_existing_tool(self):
        self.client.tool_calls['old-tool'] = {'status': 'in_progress'}
        params = {'sessionId': self.client.session, '_meta': {META: OFFER}}
        before = self.client.requests_sent
        with self.assertRaises(ProtocolError) as caught:
            await self.client.request('_session/steering', params)
        self.assertEqual(caught.exception.no_forward_receipt['id'], OFFER['id'])
        self.assertEqual(self.client.tool_calls['old-tool']['status'], 'in_progress')
        self.assertEqual(self.client.requests_sent, before + 1)
        with self.assertRaises(ProtocolError) as unrelated:
            await self.client.request('_test/unrelated', params)
        self.assertIsNone(getattr(unrelated.exception, 'no_forward_receipt', None))

    async def mutated_request(self, mode):
        params = {'sessionId': self.client.session,
                  'prompt': [{'type': 'text', 'text': mode}], '_meta': {META: dict(OFFER)}}
        pending = asyncio.create_task(self.client.request('session/prompt', params))
        try:
            async def sent():
                while self.client.active_prompt_id is None:
                    await asyncio.sleep(0)
            await asyncio.wait_for(sent(), 3)
            params['_meta'][META]['id'] = 'another-offer'
            await self.client.request('_test/release', {})
            with self.assertRaises(ProtocolError) as caught:
                await asyncio.wait_for(pending, 3)
            return caught.exception
        finally:
            if not pending.done(): pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    async def test_request_binding_retains_original_sent_offer(self):
        error = await self.mutated_request('gated-valid')
        self.assertEqual(error.no_forward_receipt['id'], 'original-offer')

    async def test_later_caller_mutation_cannot_validate_wrong_offer_receipt(self):
        error = await self.mutated_request('gated-wrong-offer')
        self.assertIsNone(getattr(error, 'no_forward_receipt', None))

    async def test_closed_transport_never_becomes_known_rejection(self):
        before = self.client.requests_sent
        with self.assertRaises((ProtocolError, asyncio.TimeoutError)) as caught:
            await self.client.prompt('closed', timeout=1, attention_offer=OFFER)
        self.assertIsNone(getattr(caught.exception, 'no_forward_receipt', None))
        self.assertEqual(self.client.requests_sent, before + 1)
        self.assertFalse(any(k == 'attention_not_forwarded' for k, _ in self.events))
