"""Optional container regression against a separate, disposable Java server.

Requires a non-production port and explicit properties/output paths. Supplies and
blocks are created only in that fixture world; never run against the workshop.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
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
    p.add_argument('--port', type=int, help='Optional translation proxy port')
    a = p.parse_args()
    properties = dict(line.split('=', 1) for line in a.properties.read_text().splitlines()
                      if '=' in line and not line.startswith('#'))
    port = int(properties['server-port'])
    assert port != 25565 and properties['level-name'] == 'container-fixture', 'Use a disposable container-fixture server, never the workshop'
    port = a.port or port
    assert port != 25565, 'Never connect fixture players to the workshop'
    a.out.parent.mkdir(parents=True, exist_ok=True)
    checks = []
    receipts = []
    with tempfile.TemporaryDirectory(prefix='container-body-') as tmp:
        cfg = {'username': 'ContainerTester', 'host': '127.0.0.1', 'port': port,
               'control_port': 18577, 'token': secrets.token_hex(32)}
        file = Path(tmp) / 'config.json'
        file.write_text(json.dumps(cfg)); os.chmod(file, 0o600)
        log = open(a.out.with_suffix('.body.log'), 'w')
        proc = subprocess.Popen([a.node, 'body.cjs', str(file)], stdout=log, stderr=log)
        def r(text):
            return command(a.properties, text)
        def act(name, **arguments):
            result = control(cfg, '/action', {'name': name, 'arguments': arguments})
            receipts.append({'tool': name, 'arguments': arguments, 'result': result})
            return result
        def denied(fragment, **kw):
            try:
                act('container', **kw)
                raise AssertionError('Expected a refused transfer')
            except urllib.error.HTTPError as e:
                assert fragment in e.read().decode()
        def fresh_turn():
            control(cfg, '/finish', {}); control(cfg, '/turn', {})
        try:
            for _ in range(100):
                try:
                    if control(cfg, '/status').get('ready'): break
                except Exception: pass
                time.sleep(.2)
            else: raise RuntimeError('Fixture body did not connect')
            for cmd in ['forceload add 0 0', 'fill 0 79 0 8 84 8 air',
                        'fill 0 80 0 8 80 8 stone', 'setblock 3 81 2 chest',
                        'tp ContainerTester 2.5 81 2.5', 'clear ContainerTester',
                        'give ContainerTester oak_planks 70', 'give ContainerTester coal 8']:
                r(cmd)
            time.sleep(.5); fresh_turn()
            chest = dict(x=3, y=81, z=2, expected='chest')
            result = act('container', **chest, operation='inspect')
            assert result['contents'] == [] and result['cursor'] is None
            result = act('container', **chest, operation='deposit', item='oak_planks', count=7)
            assert result['verified'] and result['after'] == {'source': 63, 'destination': 7}, result
            result = act('container', **chest, operation='withdraw', item='oak_planks', count=3)
            assert result['verified'] and result['after'] == {'source': 4, 'destination': 66}, result
            checks.append('Partial deposit/withdrawal: exact two-sided server deltas, ordinary inventory remainder preserved')
            result = act('container', **chest, operation='deposit', item='oak_planks', count=64)
            assert result['verified'] and result['after'] == {'source': 2, 'destination': 68}, result
            assert sum(i['count'] for i in act('container', **chest, operation='inspect')['contents']) == 68
            checks.append('64-item deposit spans source/destination stacks without exceeding requested quantity')
            denied('Insufficient source', **chest, operation='deposit', item='oak_planks', count=3)
            for slot in range(27): r(f'item replace block 3 81 2 container.{slot} with minecraft:dirt 64')
            denied('destination space', **chest, operation='deposit', item='coal', count=1)
            checks.append('Missing supplies/full destination refuse before changing inventory')
            fresh_turn()
            r('setblock 3 81 2 barrel'); time.sleep(.2)
            barrel = dict(x=3, y=81, z=2, expected='barrel')
            result = act('container', **barrel, operation='deposit', item='coal', count=8)
            assert result['verified'] and result['after'] == {'source': 0, 'destination': 8}
            result = act('container', **barrel, operation='withdraw', item='coal', count=8)
            assert result['verified'] and result['after'] == {'source': 0, 'destination': 8}
            checks.append('Barrel supports verified deposit and full withdrawal')
            r('setblock 3 81 2 chest[facing=north,type=left]')
            r('setblock 4 81 2 chest[facing=north,type=right]'); time.sleep(.2)
            result = act('container', **chest, operation='deposit', item='coal', count=5)
            assert result['verified'] and result['after']['destination'] == 5, result
            checks.append('Double chest opens the expected storage window and verifies transfer')
            r('setblock 2 82 2 stone'); time.sleep(.2)
            denied('obstructed', **chest, operation='inspect')
            r('setblock 2 82 2 air')
            checks.append('A blocked reach refuses interaction')
            fresh_turn()
            r('clear ContainerTester'); r('give ContainerTester oak_planks[minecraft:custom_name=\'"Special"\'] 2'); time.sleep(.2)
            denied('component-bearing', **chest, operation='deposit', item='oak_planks', count=1)
            checks.append('Custom-name components are refused, not silently treated as ordinary materials')
            report = {'checks': checks, 'receipts': receipts, 'server_port': port,
                      'server_inventory': r('data get entity ContainerTester Inventory'),
                      'server_container': r('data get block 3 81 2 Items'),
                      'production_world_changed': False}
            a.out.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({'checks_passed': len(checks), 'evidence': str(a.out)}))
        finally:
            proc.terminate(); proc.wait(timeout=10); log.close()


if __name__ == '__main__':
    main()
