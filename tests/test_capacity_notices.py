"""Rolling capacity and controller restarts must not flood the game chat."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import adapter


class CapacityNotices(unittest.IsolatedAsyncioTestCase):
    async def test_short_resumptions_do_not_repeat_the_notice(self):
        calls = [100.0] + [200.0] * 29
        state = {'pending_messages': 1, 'task': {'status': 'running', 'turns': 30, 'max_turns': 45}}
        before = copy.deepcopy(state)
        waiting, sent, events, observations = {}, [], [], []
        async def request(path, payload): sent.append((path, payload))
        async def sleep(delay): pass
        async def observe_wait(): observations.append('checked')
        async def gate(now):
            return await adapter.capacity_gate(calls, state, request,
                lambda kind, **data: events.append(kind), waiting, now=now, sleep=sleep,
                while_waiting=observe_wait)
        self.assertFalse(await gate(3690))
        self.assertTrue(await gate(3700))
        calls.append(3700)  # One admitted turn fills the rolling window again.
        self.assertFalse(await gate(3710))
        self.assertEqual(sent, [('/notice', {'kind': 'budget'})])
        self.assertEqual(state, before)
        self.assertEqual(len(observations), 2)
        self.assertEqual(events.count('budget_wait'), 2)
        self.assertEqual(events.count('budget_resumed'), 1)
        self.assertIn('budget_notice_suppressed', events)

    async def test_later_wait_can_notify_but_one_unbroken_wait_does_not_poll_chat(self):
        waiting, sent = {}, []
        state = {'pending_messages': 1}
        async def request(path, payload): sent.append(payload)
        async def sleep(delay): pass
        async def gate(now, full=True):
            return await adapter.capacity_gate([now-1]*30 if full else [], state,
                request, lambda *a, **k: None, waiting, now=now, sleep=sleep)
        await gate(1000)
        await gate(1900)  # Still the same wait: no recurring announcement.
        self.assertEqual(len(sent), 1)
        await gate(1901, False)
        await gate(1902)
        self.assertEqual(len(sent), 2)

    async def test_notice_attempt_survives_restart_and_ambiguous_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'capacity-notice.json'
            sent, waiting = [], {}
            async def request(url, payload):
                self.assertEqual(json.loads(path.read_text())['last_attempt_at'], 1000)
                sent.append(payload)
                raise ConnectionError('Reply lost; delivery may have happened')
            async def sleep(delay): pass
            with self.assertRaises(ConnectionError):
                await adapter.capacity_gate([999]*30, {'pending_messages': 1}, request,
                    lambda *a, **k: None, waiting, now=1000, sleep=sleep, notice_path=path)
            restarted = adapter.load_capacity_notice(path)
            await adapter.capacity_gate([1009]*30, {'pending_messages': 1}, request,
                lambda *a, **k: None, restarted, now=1010, sleep=sleep, notice_path=path)
            self.assertEqual(len(sent), 1)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    async def test_no_work_does_not_spend_a_notice_and_new_pending_chat_can_notify(self):
        waiting, sent = {}, []
        async def request(url, payload): sent.append(payload)
        async def sleep(delay): pass
        state = {'pending_messages': 0, 'task': {'status': 'budget_exhausted'}}
        await adapter.capacity_gate([999]*30, state, request, lambda *a, **k: None,
            waiting, now=1000, sleep=sleep)
        self.assertEqual(sent, [])
        state['pending_messages'] = 1
        await adapter.capacity_gate([999]*30, state, request, lambda *a, **k: None,
            waiting, now=1001, sleep=sleep)
        self.assertEqual(len(sent), 1)
        self.assertEqual(state['task']['status'], 'budget_exhausted')

    async def test_clock_rollback_does_not_suppress_forever(self):
        waiting, sent = {'last_notice_at': 100000}, []
        async def request(url, payload): sent.append(payload)
        async def sleep(delay): pass
        for now, full in [(1000, True), (1900, False), (1901, True)]:
            await adapter.capacity_gate([now-1]*30 if full else [], {'pending_messages': 1},
                request, lambda *a, **k: None, waiting, now=now, sleep=sleep)
        self.assertEqual(len(sent), 1)

    def test_missing_or_invalid_notice_cache_is_not_task_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'capacity-notice.json'
            self.assertEqual(adapter.load_capacity_notice(path), {})
            for raw in ['bad json', '[]', '{}', '{"last_attempt_at":true}', '{"last_attempt_at":NaN}']:
                path.write_text(raw)
                self.assertEqual(adapter.load_capacity_notice(path), {})
