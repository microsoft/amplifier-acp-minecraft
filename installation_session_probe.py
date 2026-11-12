"""Initialize and load only an existing binding through the official-SDK client.

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
    present = path.exists()
    saved = json.loads(path.read_text()) if present else None
    if present and not isinstance(saved, dict):
        raise ValueError('Invalid original game session; never replace malformed state')
    session = saved.get('session') if isinstance(saved, dict) else None
    if saved is not None and (not isinstance(session, str) or not session.strip()):
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
    if saved is not None and saved.get('binding') != binding:
        raise ValueError('Original game session binding changed')
    return endpoint, session, binding


def supervised_endpoint(endpoint, driver, config):
    """Keep the stored binding original; qualify only the fixed probe transport."""
    driver, config = Path(driver), Path(config)
    if not driver.is_absolute() or not config.is_absolute():
        raise ValueError('Absolute enrolled native transport paths required')
    owner = json.loads(config.read_text())
    profile = owner.get('commands', {}).get('session_endpoint', {})
    if (owner.get('version') != 1
            or [profile.get('executable'), *profile.get('args', [])] != endpoint['command']
            or profile.get('cwd') != endpoint.get('cwd')
            or type(profile.get('timeout_seconds')) is not int
            or not 1 <= profile['timeout_seconds'] <= 200):
        raise ValueError('Fixed supervised endpoint differs from original binding')
    return {**endpoint, 'command':[str(driver),'--config',str(config),
                                  'exec','--command','session_endpoint']}


async def probe(home, timeout, client_factory=None, *, idle_timeout=None, native_driver=None):
    idle_timeout = min(30, timeout) if idle_timeout is None else idle_timeout
    if not 0 < timeout <= 180 or not 0 < idle_timeout <= min(30, timeout):
        raise ValueError("Bounded verification and independent inactivity budgets required")
    original = saved_endpoint(home)
    if client_factory is None:
        if not (home/'app/acp_client.py').is_file():
            raise ValueError('Installed Minecraft client is unavailable')
        sys.path.insert(0, str(home/'app'))
        from acp_client import Client
        client_factory = Client
    endpoint, session, binding = original
    transport = supervised_endpoint(endpoint, *native_driver) if native_driver else endpoint
    client = client_factory(transport, lambda *args, **kwargs: None,
                            load_timeout=timeout, idle_timeout=idle_timeout)
    client.permission_active = lambda: False
    client.permission_tools = lambda: set()
    async def load():
        await client.start()
        if session is not None:
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
    result = {'verified':True, 'initialized':True, 'saved_session_present':session is not None,
              'saved_session_loaded':session is not None, 'new_session_created':False,
              'prompt_sent':False}
    if session is not None:
        result.update(session_id=session, binding=binding)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('--idle-timeout', type=float)
    parser.add_argument('--native-driver', type=Path)
    parser.add_argument('--native-driver-config', type=Path)
    args = parser.parse_args()
    if not args.home.is_absolute() or not 0 < args.timeout <= 180:
        parser.error('Absolute home and bounded verification timeout required')
    if bool(args.native_driver) != bool(args.native_driver_config):
        parser.error('Native driver and fixed configuration are required together')
    native=(args.native_driver,args.native_driver_config) if args.native_driver else None
    print(json.dumps(asyncio.run(probe(args.home,args.timeout,idle_timeout=args.idle_timeout,native_driver=native))))
