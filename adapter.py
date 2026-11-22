"""Deliver fresh public game chat to the installation's bound ACP session."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

from acp_client import Client
from harness_capabilities import ordinary_sources, sources
from installation_guard import durable_write
from installation_session_probe import saved_endpoint
from update_admission import held


def control(cfg, path, payload=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{cfg['control_port']}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + cfg['token'], 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=70) as response:
        return json.load(response)


def public_message(event):
    """The public game session has exactly one audience. Nothing private goes here."""
    if (not isinstance(event, dict) or event.get('whisper') is not False
            or event.get('provenance') != 'minecraft_public_chat'
            or event.get('source') not in ('human', 'agent')
            or any(not isinstance(event.get(k), str) or not event[k] for k in ('id', 'username', 'message'))):
        raise ValueError('Unexpected event in public Minecraft inbox')
    message = {key: event[key] for key in ('id', 'source', 'username', 'message')}
    message['time'] = event.get('time')
    attribution = event.get('transport')
    if isinstance(attribution, dict) and attribution.get('kind') == 'server_player_uuid' and attribution.get('username') == message['username']:
        message['server_attribution'] = {key: attribution.get(key) for key in ('kind','uuid','signature_verified')}
    else:
        message['server_attribution'] = None
    return message


async def deliver(home, event, client, binding, request, observe):
    message = public_message(event)
    facts = sources([event.get('source_fact')])
    metadata = None
    if facts and facts[0]['id'] == message['id'] and ordinary_sources(client.info):
        key = json.dumps([binding, client.session, facts], sort_keys=True).encode()
        metadata = {'version': 1, 'inputId': 'minecraft-ordinary-' + hashlib.sha256(key).hexdigest(), 'sources': facts}
    # Keep the original source even across an unknown ACK or crash. The body
    # grants exactly one claimant and never requeues it. Only that claimant
    # may write dispatch intent, before crossing the ACP transport boundary.
    event_key = hashlib.sha256(json.dumps([binding, client.session, message['id']]).encode()).hexdigest()
    directory = home / 'world-tools-delivery' / event_key
    source = {'event': message, 'session': client.session, 'binding': binding, 'source_fact': facts[0] if facts else None}
    source_file = directory / 'source.json'
    if source_file.exists():
        if json.loads(source_file.read_text()) != source:
            raise RuntimeError('Saved Minecraft event conflicts with its original source')
    else:
        durable_write(source_file, source)
    receipt_file = directory / 'delivery.json'
    ack = await request('/inbox/ack', {'id': message['id']})
    if ack.get('acknowledged') is not True or ack.get('id') != message['id']:
        raise RuntimeError('Minecraft inbox acknowledgment does not match the selected event')
    if receipt_file.exists():
        # Even a restored copy of an old inbox cannot re-dispatch a claimed event.
        observe('chat_delivery_already_recorded', event_id=message['id'], session_id=client.session)
        return
    durable_write(receipt_file, {'status': 'dispatch_intent', 'at': time.time()})
    observe('chat_delivery_started', event_id=message['id'], session_id=client.session)
    prompt = ('Public Minecraft chat. To speak in the game use a Minecraft chat tool.\n'
              + json.dumps(message, ensure_ascii=False))
    try:
        result = await client.prompt(prompt, source_metadata=metadata, snapshot_key=binding)
    except BaseException:
        durable_write(receipt_file, {'status': 'unknown', 'at': time.time()})
        observe('chat_delivery_unknown', event_id=message['id'], session_id=client.session)
        raise
    durable_write(receipt_file, {'status': 'returned', 'stop_reason': result['stop_reason'],
                                 'unsettled_tools': result.get('unsettled_tools', []), 'at': time.time()})
    observe('chat_delivery_finished', event_id=message['id'], session_id=client.session,
            stop_reason=result['stop_reason'], unsettled_tool_count=len(result.get('unsettled_tools', ())))


async def run(home):
    cfg = json.loads((home / 'config.json').read_text())
    client = None

    def observe(kind, **data):
        print(json.dumps({'time': time.time(), 'kind': kind, **data}), flush=True)

    async def request(path, payload=None):
        return await asyncio.to_thread(control, cfg, path, payload)

    try:
        while True:
            try:
                if held(home, acknowledge=True):
                    await asyncio.sleep(1)
                    continue
                event = (await request('/inbox/peek'))['event']
                if event is not None:
                    public_message(event)
                if client is None or client.transport_closed():
                    if client is not None:
                        await client.close()
                    endpoint, previous, binding = saved_endpoint(home)
                    client = Client(endpoint, observe)
                    await client.start()
                    if client.info.get('agentCapabilities', {}).get('mcpCapabilities', {}).get('http') is not True:
                        raise RuntimeError('ACP endpoint does not offer HTTP MCP')
                    if previous is None:
                        # A new session is an externally visible creation. Keep intent
                        # across crashes so a lost return cannot create another one.
                        fd = os.open(home / 'session-create.intent', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, 'w') as intent:
                            intent.write(binding)
                            intent.flush()
                            os.fsync(intent.fileno())
                        if os.name != 'nt':
                            directory = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
                            try:
                                os.fsync(directory)
                            finally:
                                os.close(directory)
                    await client.open_session(previous)
                    if previous is None:
                        durable_write(home / 'session.json', {'binding': binding, 'session': client.session})
                    client.permission_active = lambda: not held(home)
                if event is None:
                    await asyncio.sleep(1)
                    continue
                if held(home):
                    continue
                await deliver(home, event, client, binding, request, observe)
            except Exception as error:
                # The event remains in the inbox only if the body has never claimed it.
                # A later iteration may connect to deliver an independently queued event.
                observe('adapter_error', error_type=type(error).__name__, error=str(error))
                if client is not None:
                    await client.close()
                    client = None
                await asyncio.sleep(5)
    finally:
        if client is not None:
            await client.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True)
    p.add_argument('--native-owner-config',type=Path,help='Fixed installation-owned native lifecycle enrollment')
    a=p.parse_args()
    if a.native_owner_config:
        from installation_native import native_scope
        cfg=json.loads(a.native_owner_config.read_text())
        if Path(cfg['home']).resolve()!=a.home.expanduser().resolve():
            p.error('Native enrollment belongs to a different game connection')
        with native_scope(cfg):
            asyncio.run(run(a.home.expanduser()))
    else:
        asyncio.run(run(a.home.expanduser()))
