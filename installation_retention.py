"""Conservative ownership/reference collection for regenerable update artifacts.

Called under the installation provider lock. Shared plans are read-only roots;
never prune those, legacy unmarked directories, or original installation files.
"""
import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path
from installation_guard import ContinuityError, digest, durable_write, read, enrollment_ids

GRACE_SECONDS = 86400


def canonical_id(value):
    return isinstance(value, str) and str(uuid.UUID(value)) == value


class Retention:
    def __init__(self, cfg):
        self.cfg, self.root = cfg, Path(cfg['state'])
        if not self.root.is_absolute() or self.root.resolve() != self.root:
            raise ContinuityError('Owner artifact root must be direct')
        self.records = self.root/'artifact-receipts'

    def path(self, kind, identifier):
        if kind not in ('stage', 'backup') or not canonical_id(identifier):
            raise ContinuityError('Unknown owned artifact')
        return self.root/('stages' if kind == 'stage' else 'backups')/identifier

    def record_path(self, kind, identifier):
        self.path(kind, identifier)
        return self.records/(kind+'-'+identifier+'.json')

    def mark(self, kind, identifier, **values):
        path = self.record_path(kind, identifier)
        old = read(path) if path.exists() else {}
        value = {**old, 'version':1, 'kind':kind, 'id':identifier,
                 'home':self.cfg['home'], 'root':str(self.root), **values}
        durable_write(path, value)
        return value

    def owned(self, kind, identifier):
        path = self.record_path(kind, identifier)
        if path.is_symlink() or not path.is_file():
            return None
        value = read(path)
        if any(value.get(k) != v for k, v in {
                'version':1, 'kind':kind, 'id':identifier,
                'home':self.cfg['home'], 'root':str(self.root)}.items()):
            raise ContinuityError('Artifact ownership receipt changed')
        return value

    def stage_ids(self):
        for path in sorted(self.records.glob('stage-*.json')):
            identifier = path.name[len('stage-'):-len('.json')]
            if canonical_id(identifier) and self.owned('stage', identifier):
                yield identifier

    def stage_reference(self, path):
        path = Path(path).resolve()
        parent = self.root/'stages'
        if path.is_relative_to(parent) and len(path.relative_to(parent).parts):
            identifier = path.relative_to(parent).parts[0]
            if canonical_id(identifier):return identifier
        return None

    def references(self):
        """Unknown journals, links or transaction outcomes disable collection."""
        plans = Path(self.cfg['shared_plans'])
        if not plans.is_absolute() or plans.resolve() != plans or not plans.is_dir():
            raise ContinuityError('Shared plans directory unavailable or indirect')
        if plans.is_relative_to(Path(self.cfg['home'])) or plans.is_relative_to(self.root):
            raise ContinuityError('Shared plan roots must be independently owned')
        signature, stages, plan_ids = {}, set(), set()

        def document(path):
            if path.is_symlink():raise ContinuityError('Indirect reference journal')
            raw = path.read_bytes()
            signature[str(path)] = hashlib.sha256(raw).hexdigest()
            return read(path)

        state = document(plans.parent/'state.json')
        if state.get('transaction'):
            raise ContinuityError('Shared transaction is unsettled')
        if state.get('state') in ('stopping','swapping','verifying','rolling_back','recovery_required'):
            raise ContinuityError('Shared outcome is uncertain')
        for folder in sorted(plans.iterdir()):
            if not canonical_id_or_false(folder.name):continue
            if folder.is_symlink() or not folder.is_dir():
                raise ContinuityError('Indirect or malformed retained plan')
            plan_ids.add(folder.name)
            signature[str(folder)] = sorted(p.name for p in folder.iterdir())
            component = enrollment_ids(self.cfg)[1]['minecraft']
            envelope = folder/(component+'.provider.json')
            plan = document(folder/'plan.json') if (folder/'plan.json').exists() else {}
            if envelope.exists():
                value = document(envelope)
                if value.get('id') != folder.name or value.get('component') != component:
                    raise ContinuityError('Retained provider plan identity changed')
                source = value['plan']
                if source.get('available'):
                    stage = Path(source['stage'])
                    if stage.parent != self.root/'stages' or not canonical_id(stage.name):
                        raise ContinuityError('Retained stage reference is unknown')
                    stages.add(stage.name)
            elif any(c.get('id') == component and c.get('available') for c in plan.get('components', [])):
                raise ContinuityError('Retained source plan is missing')
        for key in ('plan_id','rollback_plan_id'):
            if state.get(key) and state[key] not in plan_ids:
                raise ContinuityError('Current or rollback plan is missing')
        for folder in ('transactions','provider-receipts'):
            directory = self.root/folder
            if directory.is_symlink():raise ContinuityError('Indirect transaction directory')
            for path in sorted(directory.glob('*.json')):
                value = document(path)
                if folder == 'transactions':
                    if value.get('phase') != 'restored':
                        raise ContinuityError('Participant transaction is unsettled')
                else:
                    if value.get('state') not in ('applied','rolled_back'):
                        raise ContinuityError('Source transaction is uncertain')
                    transaction = document(self.root/'transactions'/(value['transaction_id']+'.json'))
                    if transaction.get('phase') != 'restored':
                        raise ContinuityError('Source restoration is unsettled')
        for identifier in self.stage_ids():
            if self.owned('stage', identifier).get('state') in ('building', 'pruning'):
                raise ContinuityError('Artifact operation is unsettled')
        for key in ('app','venv'):
            identifier = self.stage_reference(self.cfg[key])
            if identifier:stages.add(identifier)
        backups = self.root/'backups'
        if backups.is_symlink():raise ContinuityError('Indirect backup directory')
        for backup in sorted(backups.glob('*')):
            if backup.is_symlink():raise ContinuityError('Indirect backup')
            for key in ('app','venv'):
                identifier = self.stage_reference(backup/key)
                if identifier:stages.add(identifier)
        return stages, plan_ids, signature

    def safe_path(self, kind, identifier):
        path = self.path(kind, identifier)
        if self.root.resolve() != self.root or path.parent.resolve() != path.parent or path.is_symlink():
            raise ContinuityError('Artifact path is indirect')
        if not shutil.rmtree.avoids_symlink_attacks:
            raise ContinuityError('Safe directory removal is unavailable')
        for parent, dirs, _ in os.walk(path, followlinks=False):
            if os.path.ismount(parent) or any(os.path.ismount(Path(parent)/d) for d in dirs):
                raise ContinuityError('Artifact contains a mount')
        return path

    def remove(self, kind, identifier, reason):
        if not self.owned(kind, identifier):return False
        path = self.safe_path(kind, identifier)
        self.mark(kind, identifier, state='pruning', reason=reason, pruned_at=time.time())
        if path.exists():shutil.rmtree(path)
        self.mark(kind, identifier, state='pruned')
        return True

    def prune(self, fingerprint, *, failed=None):
        if not self.cfg.get('shared_plans'):
            return {'pruned':[], 'held':'shared_plans_not_enrolled'}
        removed = []
        try:
            stages, plans, signature = self.references()
            # Only obsolete managed backup LINKS may be discarded. Real original
            # app/venv directories and unknown added files are baseline/user data.
            for backup in sorted((self.root/'backups').glob('*')):
                if not canonical_id_or_false(backup.name):continue
                record = self.owned('backup', backup.name)
                if not record or backup.name in plans:continue
                entries = list(backup.iterdir())
                if any(p.name not in ('app','venv') or not p.is_symlink()
                       or not self.stage_reference(p)
                       or not self.owned('stage', self.stage_reference(p)) for p in entries):continue
                if self.references() != (stages, plans, signature):raise ContinuityError('References changed during cleanup')
                self.remove('backup', backup.name, 'retained_plan_removed_managed_links_only')
                removed.append('backup/'+backup.name)
                stages, plans, signature = self.references()
            stages, plans, signature = self.references()
            for identifier in self.stage_ids():
                record = self.owned('stage', identifier)
                if identifier in stages or record['state'] not in ('ready','failed'):continue
                if identifier != failed and time.time()-record.get('last_offered',record['created_at']) < GRACE_SECONDS:continue
                path = self.path('stage', identifier)
                if record['state'] == 'ready':
                    manifest = read(path/'manifest.json')
                    if (digest(manifest) != record.get('manifest_hash')
                            or set(p.name for p in path.iterdir()) != {'app','venv','manifest.json'}):
                        continue
                    if any(fingerprint(path/k) != manifest['fingerprints'][k] for k in ('app','venv')):
                        continue  # Unexplained edits are not regenerable data.
                if self.references() != (stages, plans, signature):raise ContinuityError('References changed during cleanup')
                self.remove('stage', identifier, 'failed_build_unreferenced' if identifier == failed else 'unreferenced_after_grace')
                removed.append('stage/'+identifier)
            return {'pruned':removed}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ContinuityError) as error:
            return {'pruned':removed, 'held':type(error).__name__}


def canonical_id_or_false(value):
    try:return canonical_id(value)
    except (ValueError, TypeError, AttributeError):return False
