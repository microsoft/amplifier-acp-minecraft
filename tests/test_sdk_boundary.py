"""Behavioral compatibility across real official-SDK stdio endpoints."""
import asyncio
from pathlib import Path
import sys
import unittest
from acp_client import Client, ProtocolError


class SdkBoundary(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.client = Client({'command': [sys.executable, str(Path(__file__).with_name('sdk_agent_fixture.py'))],
                              'cwd': str(Path(__file__).parent.resolve())},
                             lambda kind, **data: self.events.append((kind, data)))
        await self.client.start()
        await self.client.open_session()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_sdk_peer_revisions_slow_consumer_metadata_and_terminal_drain(self):
        chunks = []
        async def slow(chunk):
            await asyncio.sleep(.01)
            chunks.append(chunk)
        result = await self.client.prompt('normal', timeout=3, on_chunk=slow)
        self.assertEqual(result['final_text'], 'new')
        self.assertEqual(chunks, ['old', 'new', ' tail'])
        self.assertIsNone(self.client.active_prompt_id)
        self.assertFalse(self.client.supports_awareness())  # vanilla peer
        self.assertFalse(self.client.supports_input_receipts())

    async def test_sdk_concurrent_extension_keeps_actual_prompt_id_and_no_receipt_claim(self):
        ready = asyncio.Event()
        async def chunk(text):ready.set()
        prompt = asyncio.create_task(self.client.prompt('concurrent', timeout=3, on_chunk=chunk))
        await asyncio.wait_for(ready.wait(), 3)
        prompt_id = self.client.active_prompt_id
        self.assertIsInstance(prompt_id, int)
        result = await self.client.request('_test/release', {'activePromptId': prompt_id})
        self.assertEqual(result['state'], 'received')
        self.assertEqual(result['source']['activePromptId'], prompt_id)
        self.assertEqual((await prompt)['final_text'], 'ready done')

    async def test_sdk_rejects_unadvertised_filesystem_callback(self):
        result = await self.client.prompt('filesystem', timeout=3)
        self.assertEqual(result['final_text'], '-32601')
        self.assertIn(('unsupported_callback', {'method': 'fs/read_text_file'}), self.events)

    async def test_sdk_load_same_session_does_not_copy_replay_into_reply(self):
        sid = self.client.session
        await self.client.open_session(sid)
        self.assertEqual(self.client.session, sid)
        self.assertNotIn('archived', (await self.client.prompt('normal', timeout=3))['text'])

    async def test_sdk_error_message_redacted_and_not_retried(self):
        before = self.client.requests_sent
        with self.assertRaisesRegex(ProtocolError, 'code -32001') as caught:
            await self.client.prompt('fail', timeout=3)
        self.assertNotIn('private', str(caught.exception))
        self.assertEqual(self.client.requests_sent, before + 1)

    async def test_sdk_wrong_session_fails_closed_even_if_terminal_follows(self):
        with self.assertRaisesRegex(ProtocolError, 'different ACP session'):
            await self.client.prompt('wrong-session', timeout=3)
        self.assertTrue(self.client.transport_closed())

    async def test_sdk_observer_failure_is_not_swallowed_by_terminal(self):
        with self.assertRaisesRegex(ProtocolError, 'observation limit'):
            await self.client.prompt('oversize', timeout=3)
        self.assertTrue(self.client.transport_closed())

    async def test_cancelled_consumer_cannot_leak_queued_updates_into_next_turn(self):
        entered = asyncio.Event()
        chunks = []
        async def blocked(chunk):
            chunks.append(chunk)
            entered.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(self.client.prompt('blocked', on_chunk=blocked))
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await self.client.cancel()
        self.assertEqual((await self.client.prompt('normal', timeout=3))['final_text'], 'new')
        self.assertEqual(chunks, ['first'])
