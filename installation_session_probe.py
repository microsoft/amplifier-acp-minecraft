"""Load only the original game binding through the installed official-SDK client.

Invoked with the installation's Python environment, while admission is closed.
No session creation, prompt, maintenance, input acknowledgment or local writes.
"""
import argparse
import asyncio
import hashlib
import json
import os
import signal
import sys
from pathlib import Path


def saved_endpoint(home):
    path = home/'session.json'
    if not path.exists():
        return None
    saved = json.loads(path.read_text())
    session = saved.get('session')
    if not isinstance(session, str) or not session.strip():
        raise ValueError('Invalid original game session; never create a replacement')
    cfg = json.loads((home/'config.json').read_text())
    endpoint = json.loads((home/'endpoint.json').read_text())
    endpoint['mcp_servers'] = [{'type':'http', 'name':'minecraft',
        'url':cfg.get('mcp_url', f"http://127.0.0.1:{cfg['control_port']}/mcp"),
        'headers':[{'name':'Authorization', 'value':'Bearer '+cfg['token']}]}]
    if cfg.get('context_provider_id'):
        endpoint['session_meta'] = {'io.github.bkrabach.conversation':{
            'provider_id':cfg['context_provider_id'], 'grant':cfg['context_grant']}}
    binding = hashlib.sha256(json.dumps(endpoint, sort_keys=True).encode()).hexdigest()
    if saved.get('binding') != binding:
        raise ValueError('Original game session binding changed')
    return endpoint, session, binding


async def probe(home, timeout, client_factory=None):
    original = saved_endpoint(home)
    if original is None:
        return {'verified':True, 'saved_session_present':False, 'saved_session_loaded':False,
                'new_session_created':False, 'prompt_sent':False}
    if client_factory is None:
        if not (home/'app/acp_client.py').is_file():
            raise ValueError('Installed Minecraft client is unavailable')
        sys.path.insert(0, str(home/'app'))
        from acp_client import Client
        client_factory = Client
    endpoint, session, binding = original
    client = client_factory(endpoint, lambda *args, **kwargs: None,
                            load_timeout=timeout, idle_timeout=timeout)
    client.permission_active = lambda: False
    client.permission_tools = lambda: set()
    async def load():
        await client.start()
        await client.open_session(session)  # Validated nonempty; never session/new.
    try:
        await asyncio.wait_for(load(), timeout)
    finally:
        try:
            await asyncio.wait_for(client.close(), 4)
        finally:
            process = getattr(client, 'process', None)
            if process is not None and process.returncode is None:
                try:
                    if os.name != 'nt':os.killpg(process.pid, signal.SIGKILL)
                    else:process.kill()
                except ProcessLookupError:
                    pass
                await asyncio.wait_for(process.wait(), 1)
    if saved_endpoint(home) != original:
        raise ValueError('Original binding changed during verification')
    return {'verified':True, 'saved_session_present':True, 'saved_session_loaded':True,
            'session_id':session, 'binding':binding, 'new_session_created':False,
            'prompt_sent':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=12)
    args = parser.parse_args()
    if not args.home.is_absolute() or not 0 < args.timeout <= 20:
        parser.error('Absolute home and bounded verification timeout required')
    print(json.dumps(asyncio.run(probe(args.home, args.timeout))))
