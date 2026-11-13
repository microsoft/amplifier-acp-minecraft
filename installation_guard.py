"""Minecraft continuity primitives for installation-owned updates.

No ACP, model, task or world operations. The installation updater supplies the
service lifecycle separately; these functions never infer permission to start it.
"""
import hashlib
import json
import os
import re
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_owner_io = ContextVar('minecraft_owner_io', default=None)


def current_owner_io():
    return _owner_io.get()


@contextmanager
def owner_io(backend):
    """Use an explicitly installed native I/O owner for this invocation only."""
    token = _owner_io.set(backend)
    try:
        yield
    finally:
        _owner_io.reset(token)


def enrollment_ids(cfg):
    """Exact installation-owned IDs let one Instance enroll multiple game connections."""
    ids = cfg.get('component_ids', {'minecraft':'minecraft', 'task-helpers':'task-helpers'})
    participant = cfg.get('participant_id', 'minecraft')
    if (not isinstance(ids, dict) or set(ids) != {'minecraft','task-helpers'}
            or any(not isinstance(v,str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}',v)
                   for v in [participant,*ids.values()])
            or len(set(ids.values())) != 2
            or {'instance','runtime','engine','container-image'} & set(ids.values())):
        raise ValueError('Invalid per-connection updater IDs')
    return participant, ids


class NotIdle(RuntimeError):
    pass


class ContinuityError(RuntimeError):
    pass


def native_service(state):
    """Recognize an exact shared-driver snapshot, without translating OS states."""
    return (state.get('schema') == 1 and isinstance(state.get('service'), dict)
            and state['service'].get('manager') in
            ('systemd_user', 'launch_agent', 'scheduled_task'))


def service_active(state):
    if native_service(state):
        return (state.get('active') is True and state.get('transitioning') is False
                and ('application' not in state or state['application'].get('status') == 'running'))
    return state.get('ActiveState') == 'active'


def service_stopped(state):
    if native_service(state):
        return (state.get('active') is False and state.get('transitioning') is False
                and state.get('processes') == []
                and ('application' not in state or state['application'].get('status') == 'absent'))
    return (state.get('ActiveState') in ('inactive', 'failed')
            and str(state.get('MainPID')) == '0')


def service_unavailable(state):
    if native_service(state):
        return state.get('masked') is not False or state.get('start_allowed') is not True
    return state.get('LoadState') == 'masked' or 'masked' in state.get('UnitFileState', '')


def service_process_identity(state):
    """The actual acknowledged controller process, never a scheduler engine PID.

    The shared driver retains native roles. A Windows task engine alone does
    not prove the Python controller identity; reject until that binding exists.
    """
    if not native_service(state):
        return state.get('process_identity')
    if not service_active(state):
        return None
    if 'application' in state:
        proof = state['application']
        identity = proof.get('identity')
        if (proof.get('status') != 'running' or not isinstance(identity, dict)
                or type(identity.get('pid')) is not int or identity['pid'] <= 0
                or len(identity) < 2 or not isinstance(proof.get('supervisor'), dict)
                or not isinstance(proof.get('manager_process'), dict)
                or not re.fullmatch('[0-9a-f]{64}', proof.get('profile_sha256', ''))):
            raise ContinuityError('Actual service application generation is not proved')
        return identity
    roles = {'systemd_user':'MainPID', 'launch_agent':'launchd_pid'}
    role = roles.get(state['service']['manager'])
    matches = [p.get('identity') for p in state.get('processes', [])
               if role is not None and p.get('role') == role]
    if (len(matches) != 1 or not isinstance(matches[0], dict)
            or type(matches[0].get('pid')) is not int or matches[0]['pid'] <= 0
            or len(matches[0]) < 2):
        raise ContinuityError('Actual service process generation is not proved')
    return matches[0]


def service_generation(state):
    if native_service(state):
        return {k:state.get(k) for k in ('service', 'active', 'transitioning', 'processes', 'application')}
    return {k:state.get(k) for k in ('MainPID', 'ExecMainStartTimestamp', 'ActiveState')}


def native_restore_evidence(state):
    keys = ('service', 'definition', 'effective_definition', 'enabled', 'start_allowed', 'masked')
    if (not native_service(state) or any(k not in state for k in keys)
            or state.get('definition_matches') is not True
            or type(state.get('start_allowed')) is not bool
            or type(state.get('masked')) is not bool):
        raise ContinuityError('Native service definition/restoration evidence is incomplete')
    # loaded changes during launchd stop/start; the registered definition and
    # independent enable/disable policy must not. Preserve raw native evidence
    # in the receipt, including unknown enabled values for static systemd units.
    return {k:state[k] for k in keys}


# Source observations can arrive while game admission is closed. These fields
# confer no execution authority. Pending inbox/participation inputs may append,
# but existing entries must not disappear or be edited during the cutover.
# Public history is a bounded retrieval cache of the same public events, not
# an input queue or work grant. Task sources and work_resumptions remain protected.
OBSERVATIONS = {'events', 'public_conversation_history', 'inbox', 'participation_pending', 'activity_pending', 'activity_tracks'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_bytes(path):
    """Read one snapshot; explicit native journal readers retain their errors."""
    native = _owner_io.get()
    if native is not None and hasattr(native, 'read_bytes'):
        return native.read_bytes(Path(path))
    return Path(path).read_bytes()


def read(path):
    return json.loads(read_bytes(path))


@contextmanager
def installation_lock(path):
    """Linux installation driver holds this across its whole lifecycle operation.

    Kernel ownership expires on a crash; the durable receipt does not. Taking
    this lock after a crash is not permission to repeat an uncertain operation.
    """
    native = _owner_io.get()
    if native is not None:
        with native.lock(Path(path)):
            yield
        return
    import fcntl
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise NotIdle('Another installation operation owns the lifecycle') from exc
        yield
    finally:
        os.close(fd)


def durable_write(path, value):
    native = _owner_io.get()
    if native is not None:
        return native.write(Path(path), value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    try:
        temporary.chmod(0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def durable_remove(path):
    native = _owner_io.get()
    if native is not None:
        return native.remove(Path(path))
    path = Path(path)
    path.unlink()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def protected_files(home):
    """Protect unknown/new accounting files too; never roll them back wholesale."""
    home = Path(home)
    files = {}
    # Source pointers and installation metadata have their own provider checks.
    excluded = {'workshop.json', 'app-source.json'}
    candidates = [p for p in home.glob('*.json') if p.name not in excluded]
    for folder in ('decisions', 'maintenance-receipts'):
        if (home/folder).is_symlink():
            raise ContinuityError('Protected state directory must not be a symlink')
        candidates.extend((home/folder).rglob('*'))
    for path in sorted(candidates):
        if path.is_symlink():
            raise ContinuityError('Protected state symlink requires explicit enrollment review')
        if path.is_file():
            files[str(path.relative_to(home))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def expiry_projection(authority):
    """Evidence for the sole status-only closure performed by WorkshopState.task.

    Hash the entire hypothetical closed record, never normalize the real record
    or write it back. Unknown/contradictory limits cannot justify a transition.
    This evidence is used only by saved-connection continuity, not by updates.
    """
    task = authority.get('task')
    if not isinstance(task, dict) or task.get('status') not in (
            'running', 'waiting', 'review', 'blocked', 'needs_review'):
        return None
    def integer(value):
        return type(value) is int and 0 <= value <= 9007199254740991
    if not integer(task.get('turns')):
        return None
    if 'bounds' in task:
        bounds = task['bounds']
        if (not isinstance(bounds, dict) or type(bounds.get('version')) is not int
                or bounds['version'] != 1 or set(bounds) != {'version','deadline_ms','max_turns'}):
            return None
        for key, field in (('deadline_ms','deadline'), ('max_turns','max_turns')):
            bound = bounds[key]
            if not isinstance(bound, dict):
                return None
            if bound == {'kind':'no_configured_bound'}:
                if field in task:return None
            elif (set(bound) != {'kind','value'} or bound['kind'] != 'finite'
                  or not integer(bound['value']) or not integer(task.get(field))
                  or task[field] != bound['value']):
                return None
    elif not integer(task.get('max_turns')):
        return None
    if not integer(task.get('deadline')):
        return None
    closed = {**task, 'status':'budget_exhausted'}
    return {'deadline_ms':task['deadline'], 'task_hash':digest(closed),
            'authority_hash':digest({**authority, 'task':closed})}


def authority_checks(before, after, *, allow_expiry=False):
    checks = {key:before[key] == after[key] for key in ('authority_hash','task_hash')}
    evidence = before.get('expiry_projection')
    observed = after.get('observed_at_ms')
    if (allow_expiry and not all(checks.values()) and isinstance(evidence, dict)
            and type(observed) is int and type(evidence.get('deadline_ms')) is int
            and observed >= evidence['deadline_ms']
            and all(after[key] == evidence.get(key) for key in checks)):
        # Both full hashes must match; identity, bounds, source, counters,
        # progress, waits, recovery and unknown effects are still unchanged.
        return {**{key:True for key in checks}, 'finite_deadline_expiry':True}
    return checks


def snapshot(home, services, body=None, status=None):
    """Read twice around the body observation in the caller to detect races.

    All saved history except the rolling event journal is protected, including
    newly added fields, pending sources, unknown receipts and sequence IDs.
    """
    history = read(Path(home)/'workshop.json')
    authority = {k: v for k, v in history.items() if k not in OBSERVATIONS}
    if body is not None and body.get('task') != history.get('task'):
        raise NotIdle('Body and saved task disagree; inspect again after settlement')
    return {
        'home': str(Path(home).resolve()),
        'authority_hash': digest(authority),
        'expiry_projection': expiry_projection(authority),
        'observed_at_ms': time.time_ns() // 1_000_000,
        'observations': {k:history.get(k) for k in OBSERVATIONS if k != 'events'},
        'task_hash': digest(history.get('task')),
        'turn': history.get('turn'),
        'sequence_states': [v.get('status') for v in history.get('action_sequences', [])],
        'protected_files': protected_files(home),
        'source_metadata': digest(read(Path(home)/'app-source.json')) if (Path(home)/'app-source.json').exists() else None,
        'services': services,
        'body': None if body is None else {k: body.get(k) for k in (
            'ready', 'busy', 'turn_active', 'action_lease', 'inventory', 'position')},
        'sequence': None if status is None else status.get('action_sequence'),
        'human_engagement': (body or {}).get('human_engagement'),
        'status_observed': isinstance(status, dict) and 'action_sequence' in status,
        'status_idle': isinstance(status, dict) and status.get('ready') is True
            and status.get('busy') is False and status.get('turn_active') is False
            and status.get('action_lease') == (body or {}).get('action_lease')
            and status.get('task') == history.get('task'),
    }


def require_idle(value):
    services = value['services']
    for kind in ('controller', 'body'):
        state = services[kind]
        if native_service(state):
            if not service_active(state) and not service_stopped(state):
                raise NotIdle('Native service is transitioning or process state is unknown')
            processes = state.get('processes')
            if (service_active(state) and (not isinstance(processes, list) or not processes
                    or any(not isinstance(p, dict) or not isinstance(p.get('identity'), dict)
                           or type(p['identity'].get('pid')) is not int or p['identity']['pid'] <= 0
                           or len(p['identity']) < 2 for p in processes))):
                raise NotIdle('Active native service has no process generation evidence')
            continue
        if state.get('ActiveState') not in ('active', 'inactive', 'failed'):
            raise NotIdle('Service is transitioning')
        if state.get('ActiveState') != 'active' and str(state.get('MainPID')) != '0':
            raise NotIdle('Stopped service still has a process')
        if state.get('ActiveState') == 'active' and not str(state.get('MainPID', '')).isdigit():
            raise NotIdle('Active process identity is unknown')
        if state.get('ActiveState') == 'active' and int(state['MainPID']) <= 0:
            raise NotIdle('Active process identity is unknown')
    if value['turn'] is not None or 'running' in value['sequence_states']:
        raise NotIdle('Saved work/sequence has not settled; never clear or replay it')
    if not service_active(services['body']):
        if service_active(services['controller']):
            raise NotIdle('Controller active without observable body')
        return
    body = value['body']
    if not body or not value['status_observed'] or not value['status_idle']:
        raise NotIdle('Active body requires fresh state and operation status')
    if body['ready'] is not True or body['busy'] is not False or body['turn_active'] is not False:
        raise NotIdle('Body is not demonstrably settled')
    lease = body.get('action_lease')
    if (not isinstance(lease, dict) or lease.get('version') != 1
            or 'lease_id' not in lease or lease['lease_id'] is not None
            or lease.get('expires_at') != 0 or lease.get('renewable') is not False):
        raise NotIdle('Action lease is active or unknown')
    if body.get('inventory') is None or body.get('position') is None:
        raise NotIdle('World continuity observation is missing')
    if value['sequence'] is not None:
        raise NotIdle('Sequence still active')


def continuity(before, after, *, body_restart=False, allow_expiry=False):
    require_idle(before)
    require_idle(after)
    authority = authority_checks(before, after, allow_expiry=allow_expiry)
    checks = {
        'same_home': before['home'] == after['home'],
        'authority': authority['authority_hash'],
        'task': authority['task_hash'],
        'files': before['protected_files'] == after['protected_files'],
    }
    if authority.get('finite_deadline_expiry'):
        checks['finite_deadline_expiry'] = True
    for key in ('inbox', 'participation_pending'):
        old=Counter(digest(item) for item in before.get('observations',{}).get(key) or [])
        new=Counter(digest(item) for item in after.get('observations',{}).get(key) or [])
        checks[key+'_retained'] = not (old-new)
    if before['body'] is not None:
        checks['world_observable'] = after['body'] is not None
        for key in ('inventory', 'position'):
            checks[key] = after['body'] is not None and before['body'][key] == after['body'][key]
    if not body_restart:
        checks['source_metadata'] = before.get('source_metadata') == after.get('source_metadata')
        checks['body_process'] = service_generation(before['services']['body']) == service_generation(after['services']['body'])
    if not all(checks.values()):
        raise ContinuityError('Update continuity changed: '+','.join(k for k, v in checks.items() if not v))
    return checks


def restore_plan(captured, current):
    """Return only justified service intentions; never unmask someone else's pause.

    Unit bytes/digests, enabled state and masks must be captured by the driver.
    A mask introduced by THIS transaction is handled by its durable receipt, not
    by this function or by a generic `systemctl unmask`.
    """
    result = {}
    for kind in ('body', 'controller'):
        old, new = captured[kind], current[kind]
        if native_service(old) or native_service(new):
            if not service_active(old) and not service_stopped(old):
                raise NotIdle('Original native service was not settled')
            if native_restore_evidence(old) != native_restore_evidence(new):
                raise ContinuityError('Native service definition or independent availability changed')
            result[kind] = 'start' if service_active(old) and not service_unavailable(old) else 'leave_stopped'
            continue
        required = ('unit_sha256', 'LoadState', 'UnitFileState', 'ActiveState')
        if any(k not in state for state in (old, new) for k in required):
            raise ContinuityError('Service restoration evidence is incomplete')
        if old.get('unit_sha256') != new.get('unit_sha256'):
            raise ContinuityError('Unit definition changed; verify candidate/rollback before restore')
        old_mask = old.get('LoadState') == 'masked' or 'masked' in old.get('UnitFileState', '')
        new_mask = new.get('LoadState') == 'masked' or 'masked' in new.get('UnitFileState', '')
        if old_mask != new_mask or old.get('UnitFileState') != new.get('UnitFileState'):
            raise ContinuityError('External mask/enabled state changed; preserve it')
        result[kind] = 'start' if old.get('ActiveState') == 'active' and not old_mask else 'leave_stopped'
    return result


class Receipt:
    """One durable operation identity; an uncertain cutover is never auto-replayed."""
    def __init__(self, path, transaction, intent):
        self.path = Path(path)
        self.transaction, self.intent = transaction, digest(intent)
        with installation_lock(str(self.path)+'.lock'):
            if self.path.exists():
                self.value = read(self.path)
                if self.value['transaction'] != transaction or self.value['intent_hash'] != self.intent:
                    raise ContinuityError('Receipt identity reused with different input')
            else:
                self.value = {'transaction': transaction, 'intent_hash': self.intent, 'state': 'new'}
                durable_write(self.path, self.value)

    def transition(self, expected, state, **facts):
        if {'transaction', 'intent_hash', 'state'} & facts.keys():
            raise ContinuityError('Receipt identity is immutable')
        with installation_lock(str(self.path)+'.lock'):
            current = read(self.path)
            if current != self.value or current['state'] not in expected:
                raise ContinuityError('Receipt state changed; inspect instead of repeating an operation')
            next_value = {**current, **facts, 'state': state}
            durable_write(self.path, next_value)
            self.value = next_value
            return next_value
