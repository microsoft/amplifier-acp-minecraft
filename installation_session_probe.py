"""Initialize and load only an existing binding through the official-SDK client.

Invoked with the installation's Python environment, while admission is closed.
No session creation, prompt, maintenance, input acknowledgment or local writes.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import signal
import sys
import types
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


def qualified_client(source):
    """Load the enrolled client and its local dependency from verified bytes.

    A packaged controller may use an overlay rather than home/app. Do not let a
    previously imported client or dependency silently substitute another source.
    The official SDK still comes from the enrolled interpreter environment.
    """
    names = ('prompt_lifecycle.py','acp_client.py')
    if (not isinstance(source, dict) or set(source) != {'directory','sha256'}
            or not isinstance(source['directory'], str) or not Path(source['directory']).is_absolute()
            or not isinstance(source['sha256'], dict) or set(source['sha256']) != set(names)
            or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v)
                   for v in source['sha256'].values())):
        raise ValueError('Enroll the exact client source directory and both SHA256 digests')
    directory = Path(source['directory'])
    contents = {name:(directory/name).read_bytes() for name in names}
    if any(hashlib.sha256(contents[name]).hexdigest() != source['sha256'][name] for name in names):
        raise ValueError('Qualified client source changed')
    modules = {}
    previous = sys.modules.get('prompt_lifecycle')
    try:
        for name in names:
            module = types.ModuleType(name[:-3])
            module.__file__ = str(directory/name)
            exec(compile(contents[name], module.__file__, 'exec'), module.__dict__)
            modules[name] = module
            if name == 'prompt_lifecycle.py':
                sys.modules['prompt_lifecycle'] = module
    finally:
        if previous is None:
            sys.modules.pop('prompt_lifecycle', None)
        else:
            sys.modules['prompt_lifecycle'] = previous
    return modules['acp_client.py'].Client


def client_source_argument(value):
    source = json.loads(value)
    if not isinstance(source, dict):
        raise ValueError('Enroll the exact client source')
    return source


async def probe(home, timeout, client_factory=None, *, idle_timeout=None, native_driver=None, client_source=None):
    idle_timeout = min(30, timeout) if idle_timeout is None else idle_timeout
    if not 0 < timeout <= 180 or not 0 < idle_timeout <= min(30, timeout):
        raise ValueError("Bounded verification and independent inactivity budgets required")
    original = saved_endpoint(home)
    if client_source is not None:
        if client_factory is not None:
            raise ValueError('Select one enrolled client factory')
        client_factory = qualified_client(client_source)
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
    parser.add_argument('--client-source', type=client_source_argument)
    args = parser.parse_args()
    if not args.home.is_absolute() or not 0 < args.timeout <= 180:
        parser.error('Absolute home and bounded verification timeout required')
    if bool(args.native_driver) != bool(args.native_driver_config):
        parser.error('Native driver and fixed configuration are required together')
    native=(args.native_driver,args.native_driver_config) if args.native_driver else None
    print(json.dumps(asyncio.run(probe(args.home,args.timeout,idle_timeout=args.idle_timeout,
                                     native_driver=native,client_source=args.client_source))))
