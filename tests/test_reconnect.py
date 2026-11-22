"""Exercise the production public inbox loop through an actual ACP subprocess."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import adapter
from installation_session_probe import saved_endpoint


def public(identity, **changes):
    return {'id': identity, 'source': 'agent', 'provenance': 'minecraft_public_chat',
            'username': 'OtherPlayer', 'message': 'One public observation.', 'whisper': False, **changes}


class Delivery(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, scenario, events, *, saved=True, ack=None, restart=False, wake_id=None):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home/'config.json').write_text(json.dumps({'control_port': 1, 'token': 'fixture'}))
            (home/'endpoint.json').write_text(json.dumps({
                'command': [sys.executable, str(Path(__file__).with_name('reconnect_fixture.py')), tmp, scenario],
                'cwd': tmp,
            }))
            if saved:
                binding = saved_endpoint(home)[2]
                (home/'session.json').write_text(json.dumps({'session': 'durable-session', 'binding': binding}))
            legacy = {'task': {'id': 'existing', 'status': 'running', 'deadline': 100}, 'inbox': ['old']}
            original = json.dumps(legacy)
            (home/'workshop.json').write_text(original)

            wakes = [{'id':wake_id,'note':'Inspect','time':'now','source':'agent_wake',
                      'session':'durable-session','binding':binding}] if wake_id else []

            def control(config, path, data=None):
                calls.append(path)
                if path == '/inbox/peek':
                    return {'event': events[0] if events else None, 'wake':wakes[0] if wakes else None}
                if path == '/wake/claim':
                    self.assertEqual(data['id'], wakes.pop()['id'])
                    return {'id':data['id'],'state':'claimed'}
                if path == '/wake/finish':
                    return {'id':data['id'],'state':'returned'}
                self.assertEqual(path, '/inbox/ack')
                self.assertEqual(data, {'id': events[0]['id']})
                if ack is not None:
                    return ack
                return {'id': events.pop(0)['id'], 'acknowledged': True}

            async def stop_on_wait(delay):
                raise asyncio.CancelledError()

            with patch.object(adapter, 'control', control), patch.object(adapter.asyncio, 'sleep', stop_on_wait), redirect_stdout(io.StringIO()):
                for _ in range(2 if restart else 1):
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(adapter.run(home), timeout=10)
            self.assertEqual((home/'workshop.json').read_text(), original)
            log = home/'requests.jsonl'
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else [], calls

    async def test_original_session_receives_only_new_public_messages_once(self):
        frames, calls = await self.exercise('keep-open', [public('1'), public('2')])
        self.assertEqual([f['method'] for f in frames], ['initialize','session/load','session/prompt','session/prompt'])
        self.assertEqual([f['session'] for f in frames[1:]], ['durable-session'] * 3)
        self.assertEqual(calls.count('/inbox/ack'), 2)

    async def test_fresh_install_creates_one_session_for_two_messages(self):
        frames, _ = await self.exercise('keep-open', [public('1'), public('2')], saved=False)
        self.assertEqual([f['method'] for f in frames], ['initialize','session/new','session/prompt','session/prompt'])

    async def test_lost_initial_session_creation_is_not_repeated_after_restart(self):
        inbox = [public('1')]
        frames, calls = await self.exercise('lost-new-result', inbox, saved=False, restart=True)
        self.assertEqual([r['method'] for r in frames], ['initialize','session/new','initialize'])
        self.assertEqual(len(inbox), 1)
        self.assertNotIn('/inbox/ack', calls)

    async def test_private_whisper_operator_and_historical_work_do_not_become_prompts(self):
        for events in ([], [public('1', whisper=True)], [public('1', source='operator')],
                       [public('1', provenance='minecraft_whisper')], [public('1', source='continuation')]):
            with self.subTest(events=events):
                frames, calls = await self.exercise('keep-open', events)
                self.assertNotIn('session/prompt', [r['method'] for r in frames])
                self.assertNotIn('/inbox/ack', calls)

    async def test_reload_refusal_preserves_pending_message(self):
        inbox = [public('1')]
        frames, calls = await self.exercise('reload-fails', inbox)
        self.assertEqual([r['method'] for r in frames], ['initialize','session/load'])
        self.assertEqual(len(inbox), 1)
        self.assertNotIn('/inbox/ack', calls)

    async def test_quiet_session_loads_tools_without_a_prompt(self):
        frames, calls = await self.exercise('keep-open', [])
        self.assertEqual([r['method'] for r in frames], ['initialize','session/load'])
        self.assertEqual(frames[1]['mcp_names'], ['minecraft'])
        self.assertEqual(calls, ['/inbox/peek'])

    async def test_ambiguous_prompt_is_claimed_and_never_resent_after_controller_restart(self):
        inbox = [public('1')]
        frames, calls = await self.exercise('during-prompt', inbox, restart=True)
        self.assertEqual([r['method'] for r in frames],
                         ['initialize','session/load','session/prompt','initialize','session/load'])
        self.assertEqual(inbox, [])
        self.assertEqual(calls.count('/inbox/ack'), 1)

    async def test_mismatched_ack_never_dispatches(self):
        frames, _ = await self.exercise('keep-open', [public('1')], ack={'id':'different','acknowledged':True})
        self.assertNotIn('session/prompt', [r['method'] for r in frames])


    async def test_negotiated_host_gets_the_original_body_source(self):
        capability = {'version': 1, 'metadata': 'com.microsoft.amplifier.source-delivery',
                      'receiptsMethod':'_amplifier/source_receipts', 'ordinaryPrompts':True,
                      'promptRetry':'inspectOnly'}
        info = {'_meta': {'io.github.bkrabach.agent-instance': {'inputContinuity': {'sourceDelivery':capability}}}}
        client = SimpleNamespace(info=info, session='original', prompt=AsyncMock(return_value={'stop_reason':'end_turn'}))
        fact = {'id':'abc', 'revision':'original-revision','occurredAt':1}
        event = public('abc', source_fact=fact)
        request = AsyncMock(return_value={'id':'abc','acknowledged':True})
        with tempfile.TemporaryDirectory() as tmp:
            await adapter.deliver(Path(tmp), event, client, 'binding', request, Mock())
            receipt, = (Path(tmp)/'world-tools-delivery').glob('*/delivery.json')
            self.assertEqual(json.loads(receipt.read_text())['status'], 'returned')
            # Simulate restoration of the old body's pre-ACK inbox.
            await adapter.deliver(Path(tmp), event, client, 'binding', request, Mock())
            self.assertEqual(client.prompt.await_count, 1)
        self.assertEqual(client.prompt.await_args.kwargs['source_metadata']['sources'], [fact])
        request.assert_awaited_with('/inbox/ack', {'id':'abc'})

    async def test_wake_no_chat_same_session_no_second_dispatch_after_unknown(self):
        wake = {'source':'agent_wake','id':'one','note':'Inspect','time':'now','session':'original','binding':'bind'}
        request = AsyncMock(return_value={'id':'one','state':'claimed'})
        client = SimpleNamespace(session='original', prompt=AsyncMock(side_effect=TimeoutError()))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                await adapter.deliver_wake(Path(tmp),wake,client,'changed',request,Mock())
            request.assert_not_awaited()
            with self.assertRaises(TimeoutError):
                await adapter.deliver_wake(Path(tmp),wake,client,'bind',request,Mock())
            await adapter.deliver_wake(Path(tmp),wake,client,'bind',request,Mock())
        client.prompt.assert_awaited_once()
        header, payload = client.prompt.await_args.args[0].split('\n')
        self.assertEqual(header, 'Agent-requested wake. Nobody spoke in the game.')
        self.assertEqual(json.loads(payload), {k:wake[k] for k in ('id','source','note','time')})

    async def test_quiet_wake_uses_original_acp_session_once(self):
        frames, calls = await self.exercise('keep-open', [], wake_id='vigil-proof', restart=True)
        prompts = [f for f in frames if f['method']=='session/prompt']
        self.assertEqual([f['session'] for f in prompts], ['durable-session'])
        self.assertEqual(calls.count('/wake/finish'), 1)
        self.assertNotIn('/inbox/ack', calls)
