#!/usr/bin/env python3
"""Fixed installation-owned lifecycle v1; never callable as an agent tool."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from installation_guard import (ContinuityError, NotIdle, continuity, digest,
                                durable_write, installation_lock, read,
                                require_idle, restore_plan, snapshot, OBSERVATIONS, enrollment_ids)
from update_admission import process_identity
from connection_state import deferred as connection_deferred

COMPONENTS = {'minecraft', 'task-helpers', 'instance', 'runtime', 'engine', 'container-image'}


def verification_seconds(cfg):
    value = cfg.get('session_verification_seconds', 12)
    if type(value) is not int or value not in (12, 180):
        raise ValueError('Session verification must explicitly select 12 or 180 seconds')
    return value


def context(value, cfg=None):
    participant_id, _ = enrollment_ids(cfg or {})
    plan = value['plan']
    if (value.get('participant') != participant_id or plan.get('schema') != 1
            or plan.get('operation') not in ('apply', 'rollback')
            or not isinstance(plan.get('components'), list)
            or any(not isinstance(v, str) for v in plan['components'])):
        raise ValueError('Unsupported installation lifecycle context')
    for key in (value['id'], plan['transaction_id']):
        if str(uuid.UUID(key)) != key:
            raise ValueError('Canonical transaction identifiers required')
    return plan


class LocalInstallation:
    def __init__(self, cfg):
        self.c = cfg
        verification_seconds(cfg)
        self.home = Path(cfg['home'])
        for key in ('home', 'state'):
            if not Path(cfg[key]).is_absolute():
                raise ValueError('Absolute installation-owned paths required')
        for kind in ('body', 'controller'):
            if not re.fullmatch(r'acp-minecraft-(body|agent)-[A-Za-z0-9_.-]+\.service', cfg['units'][kind]):
                raise ValueError('Enroll exact Minecraft unit names')

    def command(self, *args):
        return subprocess.check_output(['systemctl', '--user', *args], text=True, timeout=8)

    def services(self):
        result = {}
        for kind, unit in self.c['units'].items():
            raw = self.command('show', unit, '--property=ActiveState,MainPID,ExecMainStartTimestamp,LoadState,UnitFileState,FragmentPath')
            state = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
            fragment = state.get('FragmentPath')
            if state.get('LoadState') == 'masked':
                state['unit_sha256'] = 'masked'
            elif not fragment or not Path(fragment).is_file():
                raise ContinuityError('Unit definition is unavailable')
            else:
                state['unit_sha256'] = hashlib.sha256(self.command('cat', unit).encode()).hexdigest()
            if state.get('ActiveState') == 'active':
                state['process_identity'] = process_identity(int(state['MainPID']))
            result[kind] = state
        return result

    def action(self, kind, action):
        # Gate + controller acknowledgment is established before any stop.
        self.command(action, '--no-block', self.c['units'][kind])

    def capture(self):
        services = self.services()
        body = status = None
        before = read(self.home/'workshop.json')
        if services['body']['ActiveState'] == 'active':
            cfg = read(self.home/'config.json')
            def get(endpoint):
                request = urllib.request.Request(f"http://127.0.0.1:{int(cfg['control_port'])}/{endpoint}",
                                                 headers={'Authorization': 'Bearer '+cfg['token']})
                with urllib.request.urlopen(request, timeout=2) as response:
                    return json.load(response)
            body = get('installation-state')
            if body.get('version') != 1:
                raise ContinuityError('Body lacks installation lifecycle observation support')
            if body.get('window_open') is not False or not isinstance(body.get('inventory'), dict) or body['inventory'].get('cursor') is not None:
                raise NotIdle('Inventory window or cursor is unsettled')
            status = get('status')
        value = snapshot(self.home, services, body, status)
        # Observation can settle a naturally expired task. Retry capture instead
        # of accepting a mixture of pre/post-expiry evidence.
        after = read(self.home/'workshop.json')
        if digest({k:v for k,v in before.items() if k not in OBSERVATIONS}) != digest({k:v for k,v in after.items() if k not in OBSERVATIONS}):
            raise NotIdle('Saved state changed during observation')
        return value

    def helper(self):
        cfg = read(self.home/'config.json')
        command = (cfg.get('task_helpers') or {}).get('command')
        if command != self.c.get('task_helper') or not command or not Path(command).is_file():
            raise ContinuityError('Pure task-helper enrollment changed')
        # Generic runtime provider has verified the frozen release digest before
        # lifecycle verification. This command is static: no home/model/config.
        caps = json.loads(subprocess.check_output([command, 'helper-capabilities'], text=True, timeout=8))
        for name in ('watch', 'continuation'):
            entry = caps.get('helpers', {}).get(name, {})
            if (caps.get('schema_version') != 1 or entry.get('version') != 2
                    or entry.get('command') != name+'-v2'
                    or set(entry.get('bound_kinds', [])) != {'finite', 'no_configured_bound'}):
                raise ContinuityError('Installed helper lost required tagged-bound capabilities')
        if caps['helpers']['watch'].get('watch_ttl_seconds') != {'minimum':30, 'maximum':1800}:
            raise ContinuityError('Helper watch TTL contract changed')
        return {'sha256': hashlib.sha256(Path(command).read_bytes()).hexdigest(), 'capabilities': caps}

    def session(self, timeout):
        # Use the enrolled installation SDK, not the owner helper interpreter.
        # An unused installation still needs initialize compatibility, but must
        # stay unused: never create a replacement or prime session persistence.
        present = (self.home/'session.json').exists()
        python = Path(self.c['venv'])/'bin/python'
        script = Path(__file__).with_name('installation_session_probe.py')
        if timeout <= 7:
            raise ContinuityError('Insufficient operation budget for saved-session verification')
        value = json.loads(subprocess.check_output(
            [str(python), str(script), '--home', str(self.home),
             '--timeout', str(min(verification_seconds(self.c), timeout-6)),
             '--idle-timeout', str(min(30, verification_seconds(self.c), timeout-6))],
            text=True, timeout=timeout))
        if (value.get('verified') is not True or value.get('initialized') is not True
                or value.get('saved_session_present') is not present
                or value.get('saved_session_loaded') is not present
                or (self.home/'session.json').exists() != present
                or value.get('new_session_created') is not False or value.get('prompt_sent') is not False):
            raise ContinuityError('ACP initialization or original session verification failed')
        return value


class Participant:
    def __init__(self, cfg, envelope, backend=None):
        self.c, self.envelope = cfg, envelope
        verification_seconds(cfg)
        self.plan = context(envelope, cfg)
        self.tx = self.plan['transaction_id']
        self.root, self.home = Path(cfg['state']), Path(cfg['home'])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.backend = backend or LocalInstallation(cfg)
        self.path = self.root/'transactions'/(self.tx+'.json')
        self.gate = self.home/'installation-updates/gate.json'
        _, ids = enrollment_ids(cfg)
        shared = COMPONENTS - {'minecraft','task-helpers'}
        self.changed = shared.intersection(self.plan['components'])
        self.changed.update(role for role, identifier in ids.items() if identifier in self.plan['components'])
        self.game = 'minecraft' in self.changed
        self.value = read(self.path) if self.path.exists() else None
        if self.value and (self.value['context_hash'] != digest(envelope) or self.value['config_hash'] != digest(cfg)):
            raise ContinuityError('Transaction context changed')

    def save(self, **updates):
        self.value = {**(self.value or {}), **updates}
        durable_write(self.path, self.value)

    def gate_owned(self):
        return self.gate.exists() and read(self.gate) == {'version':1, 'transaction_id':self.tx, 'closed':True}

    def prepare(self):
        if not self.changed:
            return {'ready':True}
        if self.value and self.value['phase'] in ('ready', 'verified', 'restoring', 'restored'):
            return {'ready':True}
        if not self.value:
            if connection_deferred(self.home):
                return {'ready':False, 'reason':'saved_connection_disconnected_or_transitioning'}
            active = self.root/'active.json'
            if active.exists() and read(active)['transaction_id'] != self.tx:
                previous = self.root/'transactions'/(read(active)['transaction_id']+'.json')
                if not previous.exists() or read(previous).get('phase') != 'restored':
                    raise ContinuityError('An earlier installation transaction needs recovery')
            if self.gate.exists():
                raise ContinuityError('Preserve another admission hold')
            # Defer before closing admission, so a gap between engaged turns
            # does not itself disconnect a conversation. Existing transactions
            # keep their durable phase and must settle rather than recapture.
            observed = self.backend.capture()
            if (observed.get('human_engagement') or {}).get('active') is True:
                return {'ready':False, 'reason':'recent_human_engagement'}
            services = self.backend.services()
            # Validate captured restoration evidence before introducing any gate.
            restore_plan(services, services)
            if any(s['ActiveState']=='active' and (s.get('LoadState')=='masked' or 'masked' in s.get('UnitFileState','')) for s in services.values()):
                raise NotIdle('Preserve an already-active masked unit; automatic stop cannot restore that state')
            self.save(context_hash=digest(self.envelope), config_hash=digest(self.c), transaction_id=self.tx,
                      phase='gating', original=services, game=self.game)
            durable_write(active, {'transaction_id':self.tx})
        if self.value['phase'] == 'gating':
            if self.gate.exists() and not self.gate_owned():
                raise ContinuityError('Admission hold changed')
            durable_write(self.gate, {'version':1, 'transaction_id':self.tx, 'closed':True})
            self.save(phase='waiting')
        if not self.gate_owned():
            raise ContinuityError('Admission hold is missing or changed')
        if self.value['phase'] == 'waiting':
            services = self.backend.services()
            restore_plan(self.value['original'], services)
            old = self.value['original']['controller']
            if old['ActiveState'] == 'active':
                ack = self.home/'installation-updates/controller-idle.json'
                expected = {'transaction_id':self.tx, **old['process_identity']}
                if services['controller'].get('process_identity') != old['process_identity']:
                    raise ContinuityError('Controller changed before settlement')
                if not ack.exists() or read(ack) != expected:
                    return {'ready':False, 'reason':'busy'}
            try:
                baseline = self.backend.capture()
                require_idle(baseline)
            except NotIdle:
                return {'ready':False, 'reason':'busy'}
            self.save(phase='stopping_controller', baseline=baseline)
        if self.value['phase'] == 'stopping_controller':
            current = self.backend.services()['controller']
            if current['ActiveState'] == 'active':
                self.backend.action('controller', 'stop')
                return {'ready':False, 'reason':'busy'}
            if current['ActiveState'] not in ('inactive', 'failed') or str(current['MainPID']) != '0':
                return {'ready':False, 'reason':'busy'}
            middle = self.backend.capture()
            continuity(self.value['baseline'], middle)
            self.save(phase='stopping_body' if self.game else 'ready')
        if self.value['phase'] == 'stopping_body':
            current = self.backend.services()['body']
            if current['ActiveState'] == 'active':
                self.backend.action('body', 'stop')
                return {'ready':False, 'reason':'busy'}
            if current['ActiveState'] not in ('inactive', 'failed') or str(current['MainPID']) != '0':
                return {'ready':False, 'reason':'busy'}
            stopped = self.backend.capture()
            require_idle(stopped)
            for key in ('authority_hash', 'task_hash', 'protected_files'):
                if stopped[key] != self.value['baseline'][key]:
                    raise ContinuityError('State changed while stopping body')
            self.save(phase='ready')
        return {'ready':self.value['phase'] == 'ready'}

    def verify(self, outcome):
        started = time.monotonic()
        if not self.changed:
            return {'verified':True}
        if not self.value:
            # Worker journals attempted before invocation; process may have
            # failed before any participant mutation. Nothing to restore.
            if outcome == 'unchanged' and (not self.gate.exists() or connection_deferred(self.home)):
                return {'verified':True}
            raise ContinuityError('Missing lifecycle receipt')
        if self.value['phase'] in ('verified', 'restoring', 'restored'):
            if self.value['outcome'] != outcome:
                raise ContinuityError('Verified outcome changed')
            return {'verified':True}
        if not self.gate_owned() and self.value['phase'] != 'gating':
            raise ContinuityError('Admission hold changed before verification')
        services = self.backend.services()
        restore_plan(self.value['original'], services)
        if 'baseline' not in self.value:
            if outcome != 'unchanged':
                raise ContinuityError('Cutover lacks a settled baseline')
            # Busy prepare may be canceled while original work is still active.
            # It never stopped a unit or changed authority; remove only its gate.
            self.save(phase='verified', outcome=outcome, untouched=True)
            return {'verified':True}
        if (outcome=='unchanged' and self.value['phase']=='stopping_controller'
                and services['controller'].get('process_identity')==self.value['original']['controller'].get('process_identity')
                and services['controller']['ActiveState']=='active'):
            # Crash/failure before stop was issued: it is still the acknowledged
            # idle controller, behind our gate. No service needs restoration.
            continuity(self.value['baseline'],self.backend.capture())
            self.save(phase='verified',outcome=outcome,untouched=True)
            return {'verified':True}
        if services['controller']['ActiveState'] == 'active':
            raise ContinuityError('Controller resumed before verification')
        if self.value['original']['body']['ActiveState'] != 'active' and services['body']['ActiveState']=='active':
            raise ContinuityError('Previously stopped body was started externally')
        if self.game and self.value['original']['body']['ActiveState'] == 'active':
            self.save(phase='verifying_body')
            if services['body']['ActiveState'] in ('inactive', 'failed'):
                self.backend.action('body', 'start')
        # Bounded observation only. Repeated verify never restarts an active body.
        end = time.monotonic()+15
        while True:
            try:
                after = self.backend.capture()
                checks = continuity(self.value['baseline'], after, body_restart=self.game)
                break
            except (NotIdle, urllib.error.URLError):
                if time.monotonic() >= end:
                    raise ContinuityError('Body failed to reach verified readiness')
                time.sleep(.2)
        helper = self.backend.helper() if 'task-helpers' in self.changed else None
        session = None
        if outcome != 'unchanged' and self.changed.intersection({'instance','runtime','engine','container-image','minecraft'}):
            budget = verification_seconds(self.c)
            # The 180-second opt-in requires the owner's verified 300-second
            # shared verify hook; prepare/restore clocks remain unchanged.
            ceiling = 285 if budget == 180 else 26
            session = self.backend.session(timeout=min(budget+6, ceiling-(time.monotonic()-started)))
            # Loading must not change game authority, binding, inventory or effects.
            checks = continuity(self.value['baseline'], self.backend.capture(), body_restart=self.game)
        self.save(phase='verified', outcome=outcome, checks=checks, helper=helper, session=session)
        return {'verified':True}

    def restore(self, outcome):
        if not self.changed:
            return {'restored':True}
        if not self.value:
            return {'restored':True} if not self.gate.exists() or connection_deferred(self.home) else {'restored':False}
        if self.value.get('outcome') != outcome or self.value['phase'] not in ('verified', 'restoring', 'restored'):
            raise ContinuityError('Verify before restoration')
        if self.value['phase'] == 'restored':
            return {'restored':True}
        intentions = restore_plan(self.value['original'], self.backend.services())
        self.save(phase='restoring')  # Never reverify/rollback after this boundary.
        if self.gate.exists():
            if not self.gate_owned():
                raise ContinuityError('Do not remove another admission hold')
            self.gate.unlink()
            fd = os.open(self.gate.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        if not self.value.get('untouched'):
            for kind in ('body', 'controller'):
                services = self.backend.services()
                restore_plan(self.value['original'], services)
                if intentions[kind] == 'start' and services[kind]['ActiveState'] != 'active':
                    self.backend.action(kind, 'start')
                    # Worker can retry restoration after a transition; no rollback.
                    end = time.monotonic()+5
                    while self.backend.services()[kind]['ActiveState'] != 'active':
                        if time.monotonic() >= end:
                            return {'restored':False}
                        time.sleep(.1)
        self.save(phase='restored')
        return {'restored':True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('action', choices=('prepare', 'verify', 'restore'))
    args = parser.parse_args()
    os.umask(0o077)
    cfg = read(args.config)
    envelope = read(os.environ['CONSTELLATION_UPDATE_PLAN'])
    outcome = os.environ['CONSTELLATION_UPDATE_OUTCOME']
    if outcome not in ('unchanged', 'applied', 'rolled_back'):
        raise ValueError('Unknown lifecycle outcome')
    with installation_lock(Path(cfg['state'])/'installation.lock'):
        participant = Participant(cfg, envelope)
        result = participant.prepare() if args.action == 'prepare' else getattr(participant, args.action)(outcome)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
