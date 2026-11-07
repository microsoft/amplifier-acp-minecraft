#!/usr/bin/env python3
"""Fixed owner service-connections v1 command. No ACP prompt or task mutation.

Every service intent is journaled before dispatch. STATUS advances that same
operation using observed settlement; a lost action acknowledgement is never a
reason to issue a second action. This driver shares the updater's local lock.
"""
import argparse
from collections import Counter
import json
import os
import re
import subprocess
import sys
import time
import uuid
import urllib.request
from pathlib import Path

from connection_state import state as connection_state
from installation_guard import (ContinuityError, NotIdle, continuity, digest,
    durable_write, installation_lock, read, require_idle, restore_plan)
from installation_participant import LocalInstallation
from update_admission import process_identity


def descriptor(cfg):
    entry = cfg.get('service_connection')
    if (not isinstance(entry, dict) or set(entry) != {'id','label','revision','context_provider_ids'}
            or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', entry.get('id',''))
            or not isinstance(entry['label'],str) or not 1 <= len(entry['label']) <= 120
            or not re.fullmatch(r'[0-9a-f]{64}',entry['revision'])
            or not isinstance(entry['context_provider_ids'],list) or len(entry['context_provider_ids']) != 1
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',entry['context_provider_ids'][0])):
        raise ValueError('Enroll one exact saved Minecraft connection')
    return entry


def stored_continuity(before, after):
    # A stopped body cannot observe the server. Compare its durable state now;
    # the full inventory/position comparison is mandatory on the next Connect.
    require_idle(before)
    require_idle(after)
    checks = {key:before[key]==after[key] for key in
              ('home','authority_hash','task_hash','protected_files','source_metadata')}
    for key in ('inbox','participation_pending'):
        old = Counter(digest(x) for x in before.get('observations',{}).get(key) or [])
        new = Counter(digest(x) for x in after.get('observations',{}).get(key) or [])
        checks[key] = not (old-new)
    if not all(checks.values()):
        raise ContinuityError('Saved connection state changed: '+','.join(k for k,v in checks.items() if not v))
    return checks


class Backend(LocalInstallation):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.deadline = time.monotonic()+24

    def command(self, *args):
        remaining = self.deadline-time.monotonic()
        if remaining <= 0:raise TimeoutError('Connection invocation budget reached')
        return subprocess.check_output(['systemctl','--user',*args],text=True,timeout=min(8,remaining))

    def connected(self):
        cfg = read(self.home/'config.json')
        request = urllib.request.Request(f"http://127.0.0.1:{int(cfg['control_port'])}/status",
            headers={'Authorization':'Bearer '+cfg['token']})
        with urllib.request.urlopen(request,timeout=2) as response:
            return json.load(response).get('ready') is True

    def prepared_context_ready(self):
        prepared = self.c['prepared_context']
        agent = Path(prepared['agent_home'])
        result = subprocess.run([str(agent/'bin/agent-instance'), '--home', str(agent),
            'api', 'GET', 'context/providers'], capture_output=True, text=True, timeout=5, check=True)
        expected = prepared['provider']
        matches = [p for p in json.loads(result.stdout)['providers'] if p.get('id')==expected['id']]
        return (len(matches)==1 and all(matches[0].get(k)==v for k,v in expected.items())
                and matches[0].get('enabled',True) is True)

    def start_probe(self, result):
        job = Path(__file__).with_name('connection_session_job.py')
        process = subprocess.Popen([str(Path(self.c['venv'])/'bin/python'), str(job),
            '--home', str(self.home), '--result', str(result)], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return process_identity(process.pid)

    def probe_alive(self, identity):
        try:
            return process_identity(identity['pid']) == identity
        except (FileNotFoundError, ProcessLookupError):
            return False


class Connection:
    def __init__(self, cfg, envelope, backend=None):
        self.c, self.entry, self.e = cfg, descriptor(cfg), envelope
        if (set(envelope) != {'schema','connection_id','revision','action','request_id'}
                or envelope['schema'] != 1 or envelope['connection_id'] != self.entry['id']
                or envelope['revision'] != self.entry['revision']
                or envelope['action'] not in ('status','connect','disconnect')):
            raise ValueError('Unsupported or stale connection request')
        self.id = envelope['request_id']
        if self.id is not None and (not isinstance(self.id,str) or str(uuid.UUID(self.id)) != self.id):
            raise ValueError('Canonical request ID required')
        if self.id is None and envelope['action'] != 'status':
            raise ValueError('Connection mutation requires an operation ID')
        self.root, self.home = Path(cfg['state']), Path(cfg['home'])
        self.backend = backend or Backend(cfg)
        self.gate = self.home/'installation-updates/gate.json'
        self.marker = self.home/'installation-connections/state.json'
        self.active = self.root/'connections/active.json'
        self.path = self.root/'connections'/f'{self.id}.json' if self.id else None
        self.value = read(self.path) if self.path and self.path.exists() else None
        if self.value:
            if self.value['revision'] != self.entry['revision'] or self.value['config_hash'] != digest(cfg):
                raise ContinuityError('Connection enrollment changed during operation')
            if envelope['action'] != 'status' and envelope['action'] != self.value['action']:
                raise ContinuityError('Request ID reused with a different action')

    def save(self, **values):
        self.value = {**(self.value or {}), **values}
        durable_write(self.path, self.value)

    def mark(self, phase):
        durable_write(self.marker, {'schema':1, 'phase':phase, 'request_id':self.id})

    def result(self, state='busy', settled=False, message='', **extra):
        return {'schema':1, 'connection_id':self.entry['id'], 'request_id':self.id,
                'state':state, 'settled':settled, 'message':message, **extra}

    def gate_owned(self):
        return self.gate.exists() and read(self.gate) == {'version':1,'transaction_id':self.id,'closed':True}

    def finish(self, state, *, failed=False):
        self.save(phase='terminal', result=self.result(state,True,
            'Connection verification failed; saved state is retained.' if failed else
            'Connected; saved settings and work are retained.' if state=='connected' else
            'Disconnected; saved settings, session and work are retained.', failed=failed))
        return self.value['result']

    def status(self):
        services = self.backend.services()
        marker = connection_state(self.home)
        if self.gate.exists() or marker and marker['phase'] != 'connected':
            if marker and marker['phase']=='disconnected' and all(s['ActiveState'] in ('inactive','failed') and str(s['MainPID'])=='0' for s in services.values()):
                return self.result('disconnected', True)
            return self.result('busy', False, 'Connection is held or changing.')
        if all(s['ActiveState']=='active' for s in services.values()):
            # Active services alone are not proof of a joined player.
            if self.backend.connected():
                return self.result('connected',True)
        if all(s['ActiveState'] in ('inactive','failed') and str(s['MainPID'])=='0' for s in services.values()):
            return self.result('disconnected',True)
        return self.result('unknown',False,'Listener and game connection do not agree.')

    def start(self):
        if (self.value['action']=='connect' and self.c.get('prepared_context') is not None
                and not self.backend.prepared_context_ready()):
            return self.result(message='Owner setup must enable the matching prepared context provider after its mapped offline gate is confirmed. Nothing has been started.')
        if self.active.exists():
            prior = read(self.root/'connections'/(read(self.active)['request_id']+'.json'))
            if prior['phase'] != 'terminal':
                raise NotIdle('A previous connection operation needs reconciliation')
        update = self.root/'active.json'
        if update.exists():
            receipt = self.root/'transactions'/(read(update)['transaction_id']+'.json')
            if not receipt.exists() or read(receipt).get('phase') != 'restored':
                return self.result(message='An installation update is still in progress.')
        original = self.backend.services()
        restore_plan(original, original)
        if any(s.get('LoadState')=='masked' or 'masked' in s.get('UnitFileState','') for s in original.values()):
            raise NotIdle('An independent service mask must remain in force')
        old = connection_state(self.home)
        baseline = None
        previous_gate = None
        if self.gate.exists():
            if not old or old['phase'] != 'disconnected':
                raise NotIdle('Another operation owns admission')
            prior = read(self.root/'connections'/(old['request_id']+'.json'))
            if prior.get('phase') != 'terminal' or prior['result']['state'] != 'disconnected':
                raise ContinuityError('Disconnected intent lacks its terminal receipt')
            previous_gate = {'version':1,'transaction_id':old['request_id'],'closed':True}
            if read(self.gate) != previous_gate:
                raise ContinuityError('Disconnected admission gate changed')
            baseline = prior['baseline']
            stored_continuity(baseline, self.backend.capture())
        elif old and old['phase'] != 'connected':
            raise ContinuityError('Saved connection lost its admission gate')
        if self.value['action']=='connect' and not self.gate.exists() and self.status()['state']=='connected':
            self.save(action='connect',revision=self.entry['revision'],config_hash=digest(self.c))
            return self.finish('connected')
        self.save(revision=self.entry['revision'], config_hash=digest(self.c),
                  original=original, baseline=baseline, previous_gate=previous_gate, phase='gating')
        durable_write(self.active, {'request_id':self.id})
        return self.advance()

    def service(self, kind):
        services = self.backend.services()
        restore_plan(self.value['original'], services)
        return services[kind]

    def stopped(self, kind):
        s = self.service(kind)
        return s['ActiveState'] in ('inactive','failed') and str(s['MainPID'])=='0'

    def advance(self):
        if self.value['phase']=='accepting':
            return self.start()
        if self.value['phase']=='terminal':
            return self.value['result']
        if self.value['phase']=='gating':
            current = read(self.gate) if self.gate.exists() else None
            if current not in (self.value['previous_gate'], {'version':1,'transaction_id':self.id,'closed':True}):
                raise ContinuityError('Admission changed before connection cutover')
            durable_write(self.gate, {'version':1,'transaction_id':self.id,'closed':True})
            self.mark('disconnecting')
            self.save(phase='waiting')
        if self.value['phase'] not in ('release','await_listener') and not self.gate_owned():
            raise ContinuityError('Connection admission hold changed')
        phase = self.value['phase']
        if phase=='waiting':
            controller = self.service('controller')
            if controller['ActiveState']=='active':
                ack = self.home/'installation-updates/controller-idle.json'
                expected = {'transaction_id':self.id, **controller['process_identity']}
                if controller.get('process_identity') != self.value['original']['controller'].get('process_identity'):
                    raise ContinuityError('Controller changed before settlement')
                if not ack.exists() or read(ack)!=expected:
                    return self.result(message='Waiting for current work to settle.')
            now = self.backend.capture()
            require_idle(now)
            if self.value['baseline'] is not None:
                stored_continuity(self.value['baseline'], now)
            self.save(baseline=self.value['baseline'] or now, phase='stop_controller')
        if self.value['phase']=='stop_controller':
            self.save(phase='await_controller')  # Persist dispatch intent first.
            if not self.stopped('controller'):
                self.backend.action('controller','stop')
            return self.result()
        if self.value['phase']=='await_controller':
            if not self.stopped('controller'):return self.result()
            stored_continuity(self.value['baseline'],self.backend.capture())
            if self.value['action']=='disconnect':
                self.save(phase='context_quiesced')
                return self.result(context_quiesced=True, message='Current work is settled; context can now be closed.')
            self.save(phase='start_body')
        if self.value['phase']=='context_quiesced':
            # Host acknowledges this phase before invoking STATUS again.
            self.save(phase='stop_body')
        if self.value['phase']=='stop_body':
            self.save(phase='await_body_stop')
            if not self.stopped('body'):self.backend.action('body','stop')
            return self.result()
        if self.value['phase']=='await_body_stop':
            if not self.stopped('body'):return self.result()
            stored_continuity(self.value['baseline'],self.backend.capture())
            self.mark('disconnected')
            return self.finish('disconnected',failed=self.value.get('verification_failed',False))
        if self.value['phase']=='start_body':
            self.mark('connecting')
            self.save(phase='await_body_start')
            if self.stopped('body'):self.backend.action('body','start')
            return self.result()
        if self.value['phase']=='await_body_start':
            if self.service('body')['ActiveState']!='active':return self.result()
            now = self.backend.capture()
            stored_continuity(self.value['baseline'], now)
            checks = continuity(self.value['baseline'],now,body_restart=True)
            self.save(phase='context_ready',checks=checks)
            # The host must acknowledge this report before invoking STATUS again.
            return self.result(context_ready=True,message='Game context is ready; checking the original session next.')
        if self.value['phase']=='context_ready':
            path = self.root/'connections'/(self.id+'-session.json')
            if path.exists():raise ContinuityError('Unexpected preexisting verification result')
            self.save(phase='verifying', probe_result=str(path),probe_started=time.time())
            identity = self.backend.start_probe(path)
            self.save(probe_process=identity)
            return self.result(context_ready=True)
        if self.value['phase']=='verifying':
            path = Path(self.value['probe_result'])
            if not path.exists():
                if ('probe_process' not in self.value or not self.backend.probe_alive(self.value['probe_process'])
                        or time.time()-self.value['probe_started']>190):
                    return self.result('unknown',False,'Verification settlement is unknown; no operation has been repeated.')
                return self.result(context_ready=True,message='Original saved-session verification is in progress.')
            result = read(path)
            present = (self.home/'session.json').exists()
            if (result.get('verified') is not True or result.get('initialized') is not True
                    or result.get('saved_session_present') is not present
                    or result.get('saved_session_loaded') is not present
                    or result.get('new_session_created') is not False or result.get('prompt_sent') is not False):
                if not (result.get('verified') is False and result.get('failure_settled') is True
                        and result.get('request_method') in ('initialize','session/load')
                        and type(result.get('request_error_code')) is int
                        and result.get('new_session_created') is False and result.get('prompt_sent') is False):
                    return self.result('unknown',False,'Compatibility verification is uncertain; admission remains closed. No request or service action has been repeated.')
                self.save(phase='stop_body',verification_failed=True,session=result)
                return self.result(message='Verification failed; disconnecting without changing saved work.')
            now = self.backend.capture()
            stored_continuity(self.value['baseline'], now)
            checks = continuity(self.value['baseline'],now,body_restart=True)
            self.save(phase='release',session=result,checks=checks)
        if self.value['phase']=='release':
            # Restore-only after this boundary. Never repeat session/load or
            # compare task state after the controller may have resumed real work.
            self.service('controller')
            self.mark('connected')
            if self.gate.exists():
                if not self.gate_owned():raise ContinuityError('Do not remove another admission hold')
                self.gate.unlink()
                fd=os.open(self.gate.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
            self.save(phase='await_listener')
            if self.service('controller')['ActiveState']!='active':self.backend.action('controller','start')
            return self.result(context_ready=True)
        if self.value['phase']=='await_listener':
            if self.service('controller')['ActiveState']!='active':return self.result(context_ready=True)
            if self.service('body')['ActiveState']!='active' or not self.backend.connected():
                return self.result('unknown',message='Body lost connection before listener confirmation.')
            return self.finish('connected')
        return self.result()

    def run(self):
        if self.value:return self.advance()
        if self.e['action']=='status':
            return self.status() if self.id is None else self.result('unknown',message='No accepted operation with this ID.')
        self.save(action=self.e['action'],revision=self.entry['revision'],
                  config_hash=digest(self.c),phase='accepting')
        return self.advance()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('action',choices=('status','connect','disconnect'))
    args=parser.parse_args();os.umask(0o077)
    cfg=read(args.config);data=sys.stdin.buffer.read(65537)
    if len(data)>65536:raise ValueError('Connection envelope too large')
    envelope=json.loads(data)
    if envelope.get('action')!=args.action:raise ValueError('Command action mismatch')
    with installation_lock(Path(cfg['state'])/'installation.lock'):
        connection=Connection(cfg,envelope)
        try:result=connection.run()
        except NotIdle:result=connection.result(message='Waiting for settled game or installation state.')
    print(json.dumps(result))


if __name__=='__main__':main()
