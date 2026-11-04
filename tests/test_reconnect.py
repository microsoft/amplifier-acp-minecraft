import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import adapter
from acp_client import Client

FIXTURE = Path(__file__).with_name('reconnect_fixture.py')


class Reconnect(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, scenario):
        """Run the real scheduling loop and real ACP subprocesses against a body fixture."""
        clients, paths, finishes, sleeps = [], [], [], []
        task = {'id': 'accepted-task', 'status': 'running', 'turns': 12,
                'max_turns': 45, 'deadline': 9999999999999}
        messages = [{'id': str(i), 'source': 'human', 'message': 'Continue accepted work'} for i in (1, 2)]
        active = False
        reserved = 0
        real_sleep = asyncio.sleep

        class TrackedClient(Client):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                clients.append(self)

        def control(config, path, payload=None):
            nonlocal active, reserved
            paths.append(path)
            if path == '/state':
                if len(finishes) >= 2 or (scenario == 'during-prompt' and finishes):
                    raise asyncio.CancelledError()
                return {'ready': True, 'busy': False, 'generation': 1, 'turn_active': active,
                        'pending_messages': len(messages), 'task': dict(task)}
            if path == '/status':
                return {'turn_active': active, 'busy': False, 'task': dict(task)}
            if path == '/continuation':
                return {'action': 'continue'}
            if path == '/inbox/peek':
                return messages[:1]
            if path == '/turn':
                self.assertEqual(payload['message_ids'], [messages[0]['id']])
                messages.pop(0)
                active = True
                reserved += 1
                task['turns'] += 1
                return {}
            if path == '/finish':
                active = False
                finishes.append(dict(payload))
                # Let the asyncio process monitor receive the fixture's exit before
                # another scheduling iteration, like a completed idle service restart.
                if scenario != 'keep-open':
                    deadline = time.monotonic() + 2
                    while clients[-1].process.returncode is None and time.monotonic() < deadline:
                        time.sleep(.005)
                return {}
            return {}

        async def sleep(delay):
            sleeps.append(delay)
            if scenario == 'reload-fails' and finishes:
                raise asyncio.CancelledError()
            await real_sleep(0)

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'config.json').write_text(json.dumps({'control_port': 1, 'token': 'fixture'}))
            (home / 'endpoint.json').write_text(json.dumps({
                'command': [sys.executable, str(FIXTURE), tmp, scenario], 'cwd': tmp}))
            output = io.StringIO()
            with patch.object(adapter, 'Client', TrackedClient), patch.object(adapter, 'control', control), \
                 patch.object(adapter.asyncio, 'sleep', sleep), redirect_stdout(output):
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(adapter.run(home), timeout=10)
            frames = [json.loads(line) for line in (home / 'requests.jsonl').read_text().splitlines()]
            calls = json.loads((home / 'calls.json').read_text())
            session = json.loads((home / 'session.json').read_text())
            events = [json.loads(line) for line in output.getvalue().splitlines()]
        return {'frames': frames, 'calls': calls, 'session': session, 'events': events,
                'paths': paths, 'finishes': finishes, 'sleeps': sleeps, 'reserved': reserved,
                'messages': messages, 'task': task}

    async def test_closed_endpoint_reloads_before_reserving_another_turn(self):
        result = await self.exercise('close-between')
        methods = [v['method'] for v in result['frames']]
        self.assertEqual(methods.count('session/prompt'), 2)
        self.assertEqual(methods.count('session/new'), 1)
        self.assertEqual(methods.count('session/load'), 1)
        self.assertEqual(result['reserved'], 2)
        self.assertEqual(len(result['calls']), 2)
        self.assertTrue(all(not value['error'] for value in result['finishes']))
        self.assertEqual(result['session']['session'], 'durable-session')
        self.assertEqual({v['session'] for v in result['frames'] if v['method'] == 'session/prompt'}, {'durable-session'})
        self.assertEqual(result['task']['turns'], 14)
        self.assertEqual(result['task']['max_turns'], 45)
        self.assertEqual(result['task']['deadline'], 9999999999999)

    async def test_live_transport_is_reused_without_probe_or_replay(self):
        result = await self.exercise('keep-open')
        self.assertEqual([v['method'] for v in result['frames']],
                         ['initialize', 'session/new', 'session/prompt', 'session/prompt'])
        self.assertTrue(all(not value['error'] for value in result['finishes']))

    async def test_failed_reload_after_completed_turn_keeps_next_message_and_budget(self):
        result = await self.exercise('reload-fails')
        self.assertEqual(result['reserved'], 1)
        self.assertEqual(len(result['calls']), 1)
        self.assertEqual(len(result['finishes']), 1)
        self.assertEqual([m['id'] for m in result['messages']], ['2'])
        self.assertNotIn('/notice', result['paths'])
        self.assertEqual(result['task']['turns'], 13)
        errors = [e for e in result['events'] if e['kind'] == 'adapter_error']
        self.assertEqual([e['phase'] for e in errors], ['connection_or_scheduling'])
        self.assertIn(5, result['sleeps'])

    async def test_disconnect_during_prompt_remains_interrupted_not_automatically_replayed(self):
        result = await self.exercise('during-prompt')
        self.assertEqual(result['reserved'], 1)
        self.assertEqual(len(result['calls']), 1)
        self.assertEqual(len(result['finishes']), 1)
        self.assertTrue(result['finishes'][0]['error'])
        self.assertEqual(sum(v['method'] == 'session/prompt' for v in result['frames']), 1)
        self.assertEqual([m['id'] for m in result['messages']], ['2'])
