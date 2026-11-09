"""Optional placement checks in a loopback-only disposable fixture world.

Creates isolated terrain/supplies; never target a shared or family world.
Uses the real body and server block states, with no agent or model calls.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapter import control
from ops.rcon import command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    parser.add_argument('--properties', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--port', type=int, help='Optional loopback translation proxy')
    args = parser.parse_args()
    props = dict(line.split('=', 1) for line in args.properties.read_text().splitlines()
                 if '=' in line and not line.startswith('#'))
    assert props['level-name'] in ('facing-fixture', 'farming-fixture', 'container-fixture')
    assert props['server-ip'] == '127.0.0.1'
    port = args.port or int(props['server-port'])
    assert port not in (25565, 25566, 25567) and int(props['server-port']) not in (25565, 25566, 25567)
    report = {'world': props['level-name'], 'port': port, 'checks': [],
              'model_requests': 0, 'production_world_changed': False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); control_port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='facing-body-') as tmp:
        cfg = {'username': 'FacingTester', 'host': '127.0.0.1', 'port': port,
               'control_port': control_port, 'token': secrets.token_hex(32)}
        config = Path(tmp) / 'config.json'
        config.write_text(json.dumps(cfg)); config.chmod(0o600)
        with args.out.with_suffix('.body.log').open('w') as log:
            proc = subprocess.Popen([args.node, str(ROOT / 'body.cjs'), str(config)], stdout=log, stderr=log)
            def r(text): return command(args.properties, text)
            def act(name, **arguments):
                return control(cfg, '/action', {'name': name, 'arguments': arguments})
            try:
                for _ in range(150):
                    try:
                        if control(cfg, '/status')['ready']: break
                    except Exception: pass
                    time.sleep(.2)
                else: raise RuntimeError('Fixture body did not connect')
                for text in ['forceload add 0 0', 'fill 0 80 0 5 84 5 air',
                             'fill 0 80 0 5 80 5 stone', 'gamemode survival FacingTester',
                             'tp FacingTester 1.5 81 1.5', 'clear FacingTester']:
                    r(text)
                time.sleep(.4)
                for item in ['furnace', 'blast_furnace', 'smoker', 'oak_stairs', 'stone_brick_stairs', 'piston', 'sticky_piston']:
                    r(f'give FacingTester {item} 6'); time.sleep(.2)
                    control(cfg, '/finish', {}); control(cfg, '/turn', {})
                    for facing in ['north', 'south', 'east', 'west'] + (['up', 'down'] if 'piston' in item else []):
                        r('setblock 2 81 1 air'); time.sleep(.15)
                        result = act('place', x=2, y=81, z=1, item=item, support_face='up', facing=facing)
                        assert result['verified'] and result['properties']['facing'] == facing, result
                        confirmation = r(f'execute if block 2 81 1 minecraft:{item}[facing={facing}]')
                        assert 'Test passed' in confirmation, confirmation
                        report['checks'].append({'item': item, 'facing': facing, 'result': result,
                                                 'independent_server_confirmation': confirmation})
                for name in ['stone_button','lever']:
                    control(cfg, '/finish', {}); control(cfg, '/turn', {})
                    r(f'setblock 2 81 1 {name}[face=floor,powered=false]'); time.sleep(.2)
                    inspected=act('inspect',x=2,y=81,z=1)
                    arguments={'x':2,'y':81,'z':1,'operation_id':'fixture-'+name,'block_revision':inspected['block_revision'],'operation':'press' if name=='stone_button' else 'set'}
                    if name=='lever': arguments['powered']=True
                    result=act('activate_control',**arguments)
                    confirmation=r(f'execute if block 2 81 1 {name}[powered=true]')
                    assert result['verified'] and 'Test passed' in confirmation,(result,confirmation)
                    report['checks'].append({'control':name,'result':result,'independent_server_confirmation':confirmation})
                    if name=='stone_button':
                        time.sleep(1.5)
                        assert act('activate_control',**arguments)['duplicate']
                        assert 'Test passed' in r('execute if block 2 81 1 stone_button[powered=false]')
                    else:
                        arguments.update(operation_id='fixture-lever-off',powered=False,block_revision=act('inspect',x=2,y=81,z=1)['block_revision'])
                        assert act('activate_control',**arguments)['powered'] is False
                        assert 'Test passed' in r('execute if block 2 81 1 lever[powered=false]')
                report['passed'] = True
            finally:
                args.out.write_text(json.dumps(report, indent=2) + '\n')
                proc.terminate()
                try: proc.wait(timeout=8)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    print(json.dumps({'passed': report.get('passed', False), 'server_confirmed_placements': len(report['checks'])}))


if __name__ == '__main__':
    main()
