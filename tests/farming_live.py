"""Optional no-model till/transfer checks in a loopback-only disposable world.

Creates fixture terrain and supplies. NEVER target a shared/family world.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapter import control
from ops.rcon import command


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--node', required=True)
    p.add_argument('--properties', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--port', type=int)
    a = p.parse_args()
    properties = dict(line.split('=', 1) for line in a.properties.read_text().splitlines() if '=' in line and not line.startswith('#'))
    assert properties['level-name'] == 'farming-fixture'
    assert properties['server-ip'] == '127.0.0.1'
    port = a.port or int(properties['server-port'])
    assert port not in (25565, 25566, 25567)
    receipts = []
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); control_port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='farming-body-') as tmp:
        cfg = {'username': 'TillTester', 'host': '127.0.0.1', 'port': port,
               'control_port': control_port, 'token': secrets.token_hex(32)}
        config = Path(tmp) / 'config.json'; config.write_text(json.dumps(cfg)); os.chmod(config, 0o600)
        with a.out.with_suffix('.body.log').open('w') as log:
            proc = subprocess.Popen([a.node, 'body.cjs', str(config)], stdout=log, stderr=log)
            def r(text): return command(a.properties, text)
            def act(name, **arguments):
                result = control(cfg, '/action', {'name': name, 'arguments': arguments})
                receipts.append({'tool': name, 'arguments': arguments, 'result': result}); return result
            def denied(fragment, name, **arguments):
                try: act(name, **arguments)
                except urllib.error.HTTPError as error:
                    result = json.loads(error.read()); assert fragment in result['error'], result
                    receipts.append({'tool': name, 'rejection': result}); return
                raise AssertionError('Expected rejection')
            try:
                for _ in range(150):
                    try:
                        if control(cfg, '/status')['ready']: break
                    except Exception: pass
                    time.sleep(.2)
                else: raise RuntimeError('Fixture body did not connect')
                for text in ['forceload add 0 0', 'fill 0 79 0 5 84 5 air', 'fill 0 80 0 5 80 5 stone',
                             'setblock 2 80 1 grass_block', 'tp TillTester 1.5 81 1.5', 'clear TillTester']:
                    r(text)
                time.sleep(.4); control(cfg, '/turn', {})
                soil = {'x': 2, 'y': 80, 'z': 1, 'expected': 'grass_block'}
                denied('hoe is required', 'till', **soil)
                r('give TillTester wooden_hoe'); time.sleep(.2)
                result = act('till', **soil); assert result['verified'], result
                assert act('inspect', x=2, y=80, z=1)['name'] == 'farmland'
                confirmation = r('execute if block 2 80 1 farmland run say Fixture farmland verified')
                denied('expected grass_block or dirt', 'till', **soil)
                r('setblock 2 81 2 chest'); r('give TillTester torch 8'); time.sleep(.2)
                chest = {'x': 2, 'y': 81, 'z': 2, 'expected': 'chest'}
                old = act('container', **chest, operation='inspect')
                r('item replace block 2 81 2 container.0 with minecraft:stick 2'); time.sleep(.2)
                revision = act('conversation')['revision']
                denied('contents changed', 'container', **chest, operation='deposit', item='torch', count=8,
                       conversation_revision=revision, contents_revision=old['contents_revision'])
                current = act('container', **chest, operation='inspect')
                result = act('container', **chest, operation='deposit', item='torch', count=8,
                             conversation_revision=revision, contents_revision=current['contents_revision'])
                assert result['verified'] and result['after']['destination'] == 8, result
                assert any(i['name'] == 'stick' and i['count'] == 2 for i in result['contents'])
                report = {'checks_passed': 5, 'receipts': receipts, 'server_port': port,
                          'server_confirmation': confirmation, 'model_calls': 0, 'production_world_changed': False}
                a.out.write_text(json.dumps(report, indent=2)); print(json.dumps({k: v for k, v in report.items() if k != 'receipts'}))
            finally:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()


if __name__ == '__main__': main()
