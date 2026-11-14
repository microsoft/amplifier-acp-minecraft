"""Actual pinned SDK transport: advertised resume retains the original scope."""
import asyncio
from pathlib import Path
import sys
import unittest
from acp_client import Client, ProtocolError


class SessionResume(unittest.IsolatedAsyncioTestCase):
    async def make_client(self, *flags, **options):
        endpoint = {'command': [sys.executable, str(Path(__file__).with_name('sdk_agent_fixture.py')), *flags],
                    'cwd': str(Path(__file__).parent.resolve()),
                    'mcp_servers': [{'type': 'http', 'name': 'minecraft', 'url': 'http://127.0.0.1:1/mcp',
                                     'headers': [{'name': 'Authorization', 'value': 'fixture-only'}]}],
                    'session_meta': {'io.github.bkrabach.conversation': {
                        'provider_id': 'minecraft:fixture', 'grant': 'fixture-only'}}}
        events = []
        client = Client(endpoint, lambda kind, **data: events.append((kind, data)), **options)
        self.addAsyncCleanup(client.close)
        await client.start()
        return client, events

    async def test_fresh_connection_resumes_original_id_mcp_cwd_metadata_without_prompt(self):
        first, _ = await self.make_client('resume-only')
        await first.open_session()
        sid = first.session
        await first.close()
        client, events = await self.make_client('resume-only')
        await client.open_session(sid)
        calls = (await client.request('_test/session-calls', {}))['calls']
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call['method'], 'resume')
        self.assertEqual(call['session_id'], sid)
        self.assertEqual(call['cwd'], client.endpoint['cwd'])
        self.assertEqual(call['kwargs']['mcp_servers'], client.endpoint['mcp_servers'])
        # SDK unwraps _meta into keyword arguments and restores it on the wire.
        self.assertEqual(call['kwargs']['io.github.bkrabach.conversation'],
                         client.endpoint['session_meta']['io.github.bkrabach.conversation'])
        self.assertEqual(client.session, sid)
        self.assertFalse(client.replaying)
        self.assertFalse(client.foreground)
        self.assertIn(('session_resumed', {'session_id': sid}), events)
        self.assertEqual(client.requests_sent, 3)  # initialize, resume, read-only fixture observation

    async def test_load_still_preferred_when_both_advertised(self):
        client, events = await self.make_client()
        await client.open_session('sdk-session')
        calls = (await client.request('_test/session-calls', {}))['calls']
        self.assertEqual([c['method'] for c in calls], ['load'])
        self.assertIn(('session_loaded', {'session_id': 'sdk-session'}), events)

    async def test_absent_or_malformed_resume_refuses_without_dispatch(self):
        client, _ = await self.make_client('resume-only')
        for sessions in (None, {}, {'resume': None}, {'resume': False}, {'resume': []}, []):
            with self.subTest(sessions=sessions):
                client.info['agentCapabilities'] = {'loadSession': False, 'sessionCapabilities': sessions}
                before = client.requests_sent
                with self.assertRaisesRegex(ProtocolError, 'refusing to replace'):
                    await client.open_session('saved')
                self.assertEqual(client.requests_sent, before)

    async def test_rejection_never_falls_back_to_new_or_load(self):
        client, events = await self.make_client('resume-only', 'resume-fails')
        before = client.requests_sent
        with self.assertRaisesRegex(ProtocolError, 'session/resume rejected'):
            await client.open_session('saved')
        self.assertEqual(client.requests_sent, before + 1)
        self.assertEqual(client.session, 'saved')
        self.assertFalse(any(kind == 'session_resumed' for kind, _ in events))

    async def test_lost_response_never_replaces_saved_session(self):
        client, _ = await self.make_client('resume-only', 'resume-lost')
        before = client.requests_sent
        with self.assertRaises(ProtocolError):
            await asyncio.wait_for(client.open_session('saved'), 3)
        self.assertEqual(client.requests_sent, before + 1)
        self.assertEqual(client.session, 'saved')
        self.assertTrue(client.transport_closed())

    async def test_total_deadline_and_foreground_exclusion_apply_to_resume(self):
        client, _ = await self.make_client('resume-only', 'resume-stalls', load_timeout=.3)
        task = asyncio.create_task(client.open_session('saved'))
        while not client.foreground and not task.done():
            await asyncio.sleep(.001)
        if task.done():
            await task
        with self.assertRaisesRegex(ProtocolError, 'already active'):
            await client.request('session/prompt', {'sessionId': 'saved', 'prompt': []})
        with self.assertRaisesRegex(ProtocolError, 'session/resume exceeded'):
            await task
        self.assertEqual(client.requests_sent, 2)
        self.assertEqual(client.session, 'saved')
        self.assertFalse(client.foreground)
        self.assertFalse(client.replaying)
