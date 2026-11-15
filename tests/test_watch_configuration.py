"""Authored watches are optional: a missing decision helper must not stop the controller."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import adapter


class WatchConfiguration(unittest.IsolatedAsyncioTestCase):
    async def start(self, **config):
        """Run the real controller up to its first scheduling pause."""
        def control(cfg, path, payload=None):
            return {'ready': False} if path == '/state' else {}

        async def sleep(delay):
            raise asyncio.CancelledError()

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'config.json').write_text(json.dumps({'control_port': 1, 'token': 'fixture', **config}))
            (home / 'endpoint.json').write_text(json.dumps({'command': ['unused'], 'cwd': tmp}))
            with patch.object(adapter, 'Watches', wraps=adapter.Watches) as watches, \
                 patch.object(adapter, 'control', control), patch.object(adapter, 'Client') as client, \
                 patch.object(adapter.asyncio, 'sleep', sleep), redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(adapter.run(home), timeout=2)
                client.assert_not_called()
        notices = [json.loads(line) for line in output.getvalue().splitlines()]
        return [call.args[1] for call in watches.call_args_list], \
               [n for n in notices if n['kind'] == 'watch_decision_unavailable']

    async def test_enabled_watches_without_a_decision_helper_start_and_say_so(self):
        for config in ({}, {'decision_attention': None}, {'decision_attention': {}},
                       {'decision_attention': {'mode': 'advisory'}}):
            with self.subTest(config=config):
                bridged, notices = await self.start(agent_watches=True, **config)
                self.assertEqual(bridged, [config.get('decision_attention') or {}])
                self.assertEqual([n['reason'] for n in notices], ['decision_attention_command_not_configured'])

    async def test_configured_decision_helper_is_used_unchanged_without_a_notice(self):
        decision = {'command': '/fixture/decide', 'home': '/fixture/decision-home', 'mode': 'advisory'}
        bridged, notices = await self.start(agent_watches=True, decision_attention=decision)
        self.assertEqual(bridged, [decision])
        self.assertEqual(notices, [])

    async def test_watches_stay_off_and_silent_unless_enabled_for_work(self):
        for config in ({}, {'agent_watches': False}, {'agent_watches': True, 'incoming_chat_only': True}):
            with self.subTest(config=config):
                self.assertEqual(await self.start(**config), ([], []))
