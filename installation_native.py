"""Minecraft domain backend for the shared installation-owned native driver.

This module does not enroll services or select itself by OS. Setup supplies a
protected fixed driver configuration and an invocation-scoped official shared
Session. Domain journals retain operation identity and decide restoration.
"""
import copy
import json
import time
from contextlib import contextmanager
from pathlib import Path

from installation_guard import (ContinuityError, native_service, read,
                                service_active, service_stopped, owner_io)
from installation_participant import LocalInstallation, verification_seconds


class NativeIO:
    """Fixed roots/lock with protected publication delegated to shared code."""

    def __init__(self, cfg, session):
        self.session = session
        self.roots = {key:Path(cfg[key]) for key in ('home', 'state')}
        if any(not path.is_absolute() for path in self.roots.values()):
            raise ValueError('Native owner roots must be absolute')
        if self.roots['home'] == self.roots['state']:
            raise ValueError('Separate game and owner roots required')

    def relative(self, path):
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('Absolute non-traversing owner path required')
        matches = [(name, path.relative_to(root)) for name, root in self.roots.items()
                   if path.is_relative_to(root)]
        # Do not make overlapping roots an implicit privilege choice.
        if len(matches) != 1 or matches[0][1] == Path('.'):
            raise ValueError('Path must select one enrolled owner root child')
        name, relative = matches[0]
        return name, relative.as_posix()

    @contextmanager
    def lock(self, path):
        if Path(path) != self.roots['state']/'installation.lock':
            raise ValueError('Unenrolled native lock; no POSIX fallback')
        with self.session.lock('installation'):
            yield

    def write(self, path, value):
        root, relative = self.relative(path)
        parts = Path(relative).parts[:-1]
        for length in range(1, len(parts)+1):
            self.session.private_dir(root, Path(*parts[:length]).as_posix())
        data = json.dumps(value, sort_keys=True).encode('utf-8')
        return self.session.private_write(root, relative, data)

    def mkdir(self, path):
        root, relative = self.relative(path)
        parts = Path(relative).parts
        for length in range(1, len(parts)+1):
            self.session.private_dir(root, Path(*parts[:length]).as_posix())

    def remove(self, path):
        root, relative = self.relative(path)
        return self.session.durable_remove(root, relative)

    def tree_profile(self, kind):
        names = {'stage':'stages', 'backup':'backups'}
        if kind not in names:
            raise ContinuityError('Unknown native artifact kind')
        description = self.session.describe()
        if (type(description.get('regenerable_tree_removal')) is not int
                or description['regenerable_tree_removal'] != 1
                or not {'tree.inspect','tree.remove'}.issubset(description.get('operations', []))):
            raise ContinuityError('Native driver lacks enrolled tree removal capability')
        return names[kind]

    def tree_inspect(self, kind, identifier):
        from installation_retention import canonical_id_or_false
        if not canonical_id_or_false(identifier):
            raise ContinuityError('Native artifact must use its canonical UUID')
        return self.session.tree_inspect(self.tree_profile(kind), identifier)

    def tree_remove(self, kind, identifier, expected):
        from installation_retention import canonical_id_or_false
        if not canonical_id_or_false(identifier) or not isinstance(expected, dict):
            raise ContinuityError('Native removal requires exact artifact identity')
        return self.session.tree_remove(self.tree_profile(kind), identifier, expected)


class NativeInstallation(LocalInstallation):
    """Use raw native services with the existing Minecraft continuity checks.

    No automatic selection is made until setup/updates have qualified the
    complete backend. In particular, scheduler engine identity alone remains
    insufficient for the controller acknowledgment on Windows.
    """

    def __init__(self, cfg, session):
        self.c, self.native = cfg, session
        verification_seconds(cfg)
        self.home = Path(cfg['home'])
        for key in ('home', 'state'):
            if not Path(cfg[key]).is_absolute():
                raise ValueError('Absolute installation-owned paths required')
        native = cfg['native_platform']
        if (native.get('version') != 1 or native.get('services') !=
                {'body':'body', 'controller':'controller'}):
            raise ValueError('Enroll exact native body/controller names')
        self.python = Path(native['python'])
        if not self.python.is_absolute():
            raise ValueError('Enroll the exact private Python executable')
        self.names = native['services']
        self.observed = {}

    def session_python(self):
        return self.python

    def session_arguments(self):
        native=self.c['native_platform']
        return ['--native-driver',native['driver'],'--native-driver-config',native['config']]

    def services(self):
        states = {kind:self.native.service_snapshot(name) for kind,name in self.names.items()}
        if any(not native_service(state) for state in states.values()):
            raise ContinuityError('Native driver returned an unsupported service snapshot')
        self.observed = copy.deepcopy(states)
        return states

    def action(self, kind, action):
        if kind not in self.names or action not in ('start', 'stop') or kind not in self.observed:
            raise ContinuityError('Observe the exact enrolled service before control')
        expected = self.observed[kind]
        if not service_active(expected) and not service_stopped(expected):
            raise ContinuityError('Service control requires settled native evidence')
        # Unknown/rejected transport is propagated. Do not refresh the expected
        # snapshot and silently redispatch after a compare failure.
        self.observed.pop(kind, None)
        result = self.native.service_action(self.names[kind], action, expected)
        if result != {'accepted':True}:
            raise ContinuityError('Native service request has no affirmative acceptance')
        return result

    def command(self, *args):
        raise ContinuityError('Native backend cannot fall back to systemctl')


def validate_driver_mapping(cfg, driver_config):
    """Bind domain paths to the protected driver's names before invocation."""
    actual = read(driver_config)
    if actual.get('version') != 1:
        raise ValueError('Unsupported protected native driver configuration')
    roots = actual.get('roots', {})
    if any(roots.get(name) != cfg[name] for name in ('home', 'state')):
        raise ValueError('Native root mapping differs from the domain installation')
    if actual.get('locks', {}).get('installation') != str(Path(cfg['state'])/'installation.lock'):
        raise ValueError('Native installation lock mapping differs')
    if any(name not in actual.get('services', {}) for name in ('body', 'controller')):
        raise ValueError('Native body/controller services are not enrolled')
    requested = cfg['native_platform'].get('regenerable_tree_removal')
    if requested is not None:
        if type(requested) is not int or requested != 1:
            raise ValueError('Unsupported native tree removal enrollment')
        expected = {name:{'root':'state','path':name,'lock':'installation'}
                    for name in ('stages','backups')}
        if any(actual.get('regenerable_trees', {}).get(name) != value
               for name,value in expected.items()):
            raise ValueError('Native regenerable roots differ from domain staging')


def connection_backend(cfg, session):
    # Import lazily: the default Linux connection backend does not need the
    # shared Python package or native service enrollment.
    from installation_connection import Backend

    class NativeConnection(NativeInstallation, Backend):
        def __init__(self):
            NativeInstallation.__init__(self, cfg, session)
            self.deadline = time.monotonic()+24

        def start_probe(self, result):
            root, relative = NativeIO(cfg, session).relative(result)
            if root != 'state' or Path(result).exists():
                raise ContinuityError('Fresh owner-state probe result required')
            # The protected profile fixes Python, job, home and owner config.
            # The connection journal already persisted this one launch intent.
            return session.launch('session_probe', result=relative)

        def probe_alive(self, identity):
            return session.process_matches(identity)

    return NativeConnection()


@contextmanager
def native_scope(cfg, *, session_factory=None):
    """Explicit owner enrollment only; never inferred from the host OS."""
    native = cfg['native_platform']
    driver, config = Path(native['driver']), Path(native['config'])
    if native.get('version') != 1 or not driver.is_absolute() or not config.is_absolute():
        raise ValueError('Exact absolute native driver/config enrollment required')
    validate_driver_mapping(cfg, config)
    if session_factory is None:
        from constellation_native import Session
        session_factory = Session
    with session_factory(driver, config) as session:
        description = session.describe()
        required = {'lock.acquire','lock.release','process.identity','service.snapshot',
                    'service.action','storage.write','storage.mkdir','storage.remove'}
        if description.get('protocol') != 1 or not required.issubset(description.get('operations', [])):
            raise ContinuityError('Installed native driver lacks the required interface')
        with owner_io(NativeIO(cfg, session)):
            yield session
