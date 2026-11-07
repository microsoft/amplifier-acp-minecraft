"""Minecraft continuity primitives for installation-owned updates.

No ACP, model, task or world operations. The installation updater supplies the
service lifecycle separately; these functions never infer permission to start it.
"""
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class NotIdle(RuntimeError):
    pass


class ContinuityError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


@contextmanager
def installation_lock(path):
    """Linux installation driver holds this across its whole lifecycle operation.

    Kernel ownership expires on a crash; the durable receipt does not. Taking
    this lock after a crash is not permission to repeat an uncertain operation.
    """
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


def protected_files(home):
    """Protect unknown/new accounting files too; never roll them back wholesale."""
    home = Path(home)
    files = {}
    # Source pointers and installation metadata have their own provider checks.
    excluded = {'workshop.json', 'app-source.json', 'installation.json'}
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


def snapshot(home, services, body=None, status=None):
    """Read twice around the body observation in the caller to detect races.

    All saved history except the rolling event journal is protected, including
    newly added fields, pending sources, unknown receipts and sequence IDs.
    """
    history = read(Path(home)/'workshop.json')
    authority = {k: v for k, v in history.items() if k != 'events'}
    if body is not None and body.get('task') != history.get('task'):
        raise NotIdle('Body and saved task disagree; inspect again after settlement')
    return {
        'home': str(Path(home).resolve()),
        'authority_hash': digest(authority),
        'task_hash': digest(history.get('task')),
        'turn': history.get('turn'),
        'sequence_states': [v.get('status') for v in history.get('action_sequences', [])],
        'protected_files': protected_files(home),
        'services': services,
        'body': None if body is None else {k: body.get(k) for k in (
            'ready', 'busy', 'turn_active', 'action_lease', 'inventory', 'position')},
        'sequence': None if status is None else status.get('action_sequence'),
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
    if services['body']['ActiveState'] != 'active':
        if services['controller']['ActiveState'] == 'active':
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


def continuity(before, after, *, body_restart=False):
    require_idle(before)
    require_idle(after)
    checks = {
        'same_home': before['home'] == after['home'],
        'authority': before['authority_hash'] == after['authority_hash'],
        'task': before['task_hash'] == after['task_hash'],
        'files': before['protected_files'] == after['protected_files'],
    }
    if before['body'] is not None:
        checks['world_observable'] = after['body'] is not None
        for key in ('inventory', 'position'):
            checks[key] = after['body'] is not None and before['body'][key] == after['body'][key]
    if not body_restart:
        checks['body_process'] = all(
            before['services']['body'].get(k) == after['services']['body'].get(k)
            for k in ('MainPID', 'ExecMainStartTimestamp', 'ActiveState'))
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
