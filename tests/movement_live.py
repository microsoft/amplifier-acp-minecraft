"""Optional movement regression in a separate, disposable fixture world.

RCON prepares geometry; every tested movement uses the adapter's ordinary body.
No agent runtime or model requests are involved.
"""
import argparse
import json
import math
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapter import control
from ops.rcon import command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    parser.add_argument('--properties', required=True, type=Path)
    parser.add_argument('--port', type=int, help='Optional loopback translation proxy')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    properties = dict(line.split('=', 1) for line in args.properties.read_text().splitlines()
                      if '=' in line and not line.startswith('#'))
    port = args.port or int(properties['server-port'])
    assert properties['level-name'] in ('movement-fixture', 'container-fixture')
    assert properties['server-ip'] == '127.0.0.1', 'Fixture must be loopback-only'
    assert port not in (25565, 25566, 25567) and int(properties['server-port']) not in (25565, 25566, 25567)
    report = {'world': properties['level-name'], 'port': port, 'checks': [], 'receipts': [],
              'model_requests': 0, 'production_world_changed': False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='movement-body-') as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            control_port = sock.getsockname()[1]
        cfg = {'username': 'ContainerTester', 'host': '127.0.0.1', 'port': port,
               'control_port': control_port, 'token': secrets.token_hex(32)}
        config = Path(tmp) / 'config.json'
        config.write_text(json.dumps(cfg)); config.chmod(0o600)
        log = args.out.with_suffix('.body.log').open('w')
        proc = subprocess.Popen([args.node, str(ROOT / 'body.cjs'), str(config)], stdout=log, stderr=log)

        def rcon(text):
            return command(args.properties, text)

        def act(name, **arguments):
            result = control(cfg, '/action', {'name': name, 'arguments': arguments})
            report['receipts'].append({'action': name, 'arguments': arguments, 'result': result})
            return result

        def turn():
            control(cfg, '/finish', {}); control(cfg, '/turn', {})

        def teleport(x, y, z):
            rcon(f'tp ContainerTester {x + .5} {y} {z + .5}')
            time.sleep(.6)

        def arrive(x, y, z):
            result = act('move', x=x, y=y, z=z, range=0)
            assert result['reached'] and tuple(math.floor(result['position'][a]) for a in ('x', 'y', 'z')) == (x, y, z), result
            # Independent server-side coordinates, not only the bot's prediction.
            reply = rcon('data get entity ContainerTester Pos')
            position = [float(v.strip().rstrip('d')) for v in reply.split('[', 1)[1].split(']', 1)[0].split(',')]
            assert tuple(math.floor(v) for v in position) == (x, y, z), reply
            report['receipts'][-1]['server_position'] = position

        try:
            for _ in range(150):
                try:
                    if control(cfg, '/status').get('ready'):
                        break
                except Exception:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError('Fixture player did not connect')
            rcon('forceload add -48 32 -16 64')
            rcon('gamemode survival ContainerTester')
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                # A three-level staircase, both positive and negative coordinates.
                rcon('fill -48 79 32 -16 88 64 air')
                rcon('fill -48 80 32 -16 80 64 stone')
                x, z = -32, 48
                for step in range(1, 4):
                    for side in range(-1, 2):
                        bx, bz = x + dx * step + dz * side, z + dz * step + dx * side
                        rcon(f'fill {bx} 81 {bz} {bx} {80 + step} {bz} stone')
                teleport(x, 81, z); turn()
                arrive(x + dx * 3, 84, z + dz * 3)
                arrive(x, 81, z)
                report['checks'].append(f'Three full-block rises and descent, direction {dx},{dz}, server-confirmed')
            turn()
            rcon('fill -48 81 32 -16 88 64 air')
            teleport(-36, 81, 44)
            arrive(-34, 81, 47)
            report['checks'].append('Level walking still reaches the requested feet position')
            rcon('fill -33 81 46 -31 81 48 stone')
            rcon('fill -33 83 46 -31 83 48 stone')
            result = act('plan_route', x=-32, y=82, z=47, range=0)
            assert not result['reachable'], result
            report['checks'].append('A rise with blocked head clearance remains unreachable')
            report['passed'] = True
        finally:
            args.out.write_text(json.dumps(report, indent=2) + '\n')
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            log.close()
    print(json.dumps({'passed': report.get('passed', False), 'checks': report['checks']}))


if __name__ == '__main__':
    main()
