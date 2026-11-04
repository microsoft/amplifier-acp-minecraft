"""Planner capacity must not hide short-lived evidence from bounded attention."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import adapter


class CapacityObservation(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, notification=False, pending_message=False, stopped=False, expired=False, exhausted=False, busy=False):
        paths, events, polls, wakes = [], [], [], []
        task = {'id': 'accepted', 'status': 'stopped' if stopped else 'waiting',
                'turns': 45 if exhausted else 30, 'max_turns': 45,
                'deadline': int(time.time() * 1000) + (-1 if expired else 3600000)}
        original = dict(task)
        calls = [time.time()] * 30
        message = [{'id': 'pending', 'source': 'human', 'message': 'A queued question'}] if pending_message else []

        class Watches:
            def __init__(self, *args):
                pass

            async def poll(self):
                polls.append('checked')

            async def pending(self):
                return [{'id': 'delivery-watch', 'task_id': 'accepted'}] if notification else []

            async def managed(self):
                return True

        def control(cfg, path, payload=None):
            paths.append(path)
            if path == '/state':
                return {'ready': True, 'busy': busy, 'turn_active': False,
                        'generation': 7, 'pending_messages': len(message), 'task': dict(task)}
            if path == '/continuation':
                return {'action': 'hold'}
            if path == '/inbox/peek':
                return message
            if path == '/wake':
                self.assertEqual(payload, {'task_id': 'accepted', 'generation': 7})
                task['status'] = 'running'
                wakes.append(payload)
            if path in ['/turn', '/inbox', '/finish']:
                self.fail('Capacity must not admit a prompt or consume queued work: ' + path)
            return {}

        async def sleep(delay):
            raise asyncio.CancelledError()

        original_gate = adapter.capacity_gate

        async def gate(*args, **kwargs):
            return await original_gate(*args, sleep=sleep, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'config.json').write_text(json.dumps({'control_port': 1, 'token': 'fixture',
                                                        'agent_watches': True, 'decision_attention': {}}))
            (home / 'endpoint.json').write_text(json.dumps({'command': ['unused'], 'cwd': tmp}))
            (home / 'calls.json').write_text(json.dumps(calls))
            (home / 'session.json').write_text(json.dumps({'binding': 'existing', 'session': 'saved'}))
            original_session = (home / 'session.json').read_bytes()
            with patch.object(adapter, 'Watches', Watches), patch.object(adapter, 'control', control), \
                 patch.object(adapter, 'Client') as client, patch.object(adapter.asyncio, 'sleep', sleep), \
                 patch.object(adapter, 'capacity_gate', gate), \
                 redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(adapter.run(home), timeout=2)
                client.assert_not_called()
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(json.loads((home / 'calls.json').read_text()), calls)
            self.assertEqual((home / 'session.json').read_bytes(), original_session)
        for key in ['id', 'turns', 'max_turns', 'deadline']:
            self.assertEqual(task[key], original[key])
        return polls, wakes, task, events, message

    async def test_delivery_is_observed_while_planner_capacity_is_full(self):
        polls, wakes, task, events, _ = await self.exercise(notification=True)
        self.assertEqual(polls, ['checked'])
        self.assertEqual(len(wakes), 1)
        self.assertEqual(task['status'], 'running')
        self.assertTrue(any(e['kind'] == 'watch_applied' and e['application'] == 'wake' for e in events))
        self.assertFalse(any(e['kind'] == 'turn_started' for e in events))

    async def test_a_hold_keeps_waiting_without_starting_the_agent(self):
        polls, wakes, task, _, _ = await self.exercise()
        self.assertEqual(polls, ['checked'])
        self.assertEqual(wakes, [])
        self.assertEqual(task['status'], 'waiting')

    async def test_queued_message_stays_queued_while_attention_can_notice_delivery(self):
        polls, wakes, _, _, messages = await self.exercise(notification=True, pending_message=True)
        self.assertEqual(polls, ['checked'])
        self.assertEqual(len(wakes), 1)
        self.assertEqual([v['id'] for v in messages], ['pending'])

    async def test_stopped_work_is_not_observed_or_woken(self):
        polls, wakes, task, _, _ = await self.exercise(notification=True, stopped=True)
        self.assertEqual(polls, [])
        self.assertEqual(wakes, [])
        self.assertEqual(task['status'], 'stopped')

    async def test_expired_or_exhausted_work_is_not_observed_or_woken(self):
        for flag in ['expired', 'exhausted']:
            with self.subTest(flag=flag):
                polls, wakes, _, _, _ = await self.exercise(notification=True, **{flag: True})
                self.assertEqual(polls, [])
                self.assertEqual(wakes, [])

    async def test_unsettled_body_is_not_woken_during_capacity_wait(self):
        polls, wakes, _, _, _ = await self.exercise(notification=True, busy=True)
        self.assertEqual(polls, [])
        self.assertEqual(wakes, [])
