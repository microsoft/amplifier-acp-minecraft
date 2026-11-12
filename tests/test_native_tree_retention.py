"""Domain contract tests; native no-follow/ACL behavior belongs to the driver.

The fake storage/tree peer uses disposable directories only. Actual candidate
driver composition is recorded separately; this is not six-platform proof.
"""
import contextlib
import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from installation_guard import ContinuityError, installation_lock, owner_io, read
from installation_native import NativeIO, validate_driver_mapping
from test_installation_retention import RetentionTests as _Fixture


class LostReply(RuntimeError):
    pass


class TreePeer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.locked = False
        self.closed = False
        self.calls = []
        self.unknown = False
        self.advertised = 1
        self.on_remove = None

    def check(self):
        if self.closed:
            raise AssertionError('No dispatch on the lost Session')

    @contextlib.contextmanager
    def lock(self, name):
        self.check()
        assert name == 'installation'
        self.locked = True
        try:
            yield
        finally:
            self.locked = False

    def describe(self):
        self.check()
        return {'regenerable_tree_removal':self.advertised,
                'operations':['tree.inspect','tree.remove']}

    def private_dir(self, root, path):
        self.check()
        (Path(self.cfg[root])/path).mkdir(parents=True, exist_ok=True)

    def private_write(self, root, path, data):
        self.check()
        assert self.locked
        self.calls.append(('write', path))
        (Path(self.cfg[root])/path).write_bytes(data)

    def tree_inspect(self, name, entry):
        self.check()
        self.calls.append(('inspect', name, entry))
        path = Path(self.cfg['state'])/name/entry
        if not path.exists():
            return None
        return {'opaque_fixture_identity':path.stat().st_ino, 'profile':name}

    def tree_remove(self, name, entry, expected, **kwargs):
        self.check()
        assert self.locked
        self.calls.append(('remove', name, entry, copy.deepcopy(expected)))
        self.removal_timeout = kwargs.get('timeout')
        kind = {'stages':'stage','backups':'backup'}[name]
        record = read(Path(self.cfg['state'])/'artifact-receipts'/(kind+'-'+entry+'.json'))
        assert record['state'] == 'pruning' and record['expected_tree'] == expected
        if self.on_remove:
            self.on_remove()
        if self.unknown:
            self.closed = True
            self.locked = False
            raise LostReply('transport_timeout')
        path = Path(self.cfg['state'])/name/entry
        if self.tree_inspect(name, entry) != expected:
            raise ContinuityError('Replaced tree')
        shutil.rmtree(path)
        return {'absent':True}


class NativeTreeRetentionTests(unittest.TestCase):
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    stage = _Fixture.stage
    age = _Fixture.age
    retain = _Fixture.retain

    def native(self):
        self.cfg['native_platform'] = {'version':1,'regenerable_tree_removal':1}
        peer = TreePeer(self.cfg)
        return peer, NativeIO(self.cfg, peer)

    def test_allocation_and_reuse_inspect_without_python_removal_guard(self):
        plan = self.stage()
        peer, native = self.native()
        existing = Path(plan['stage']).name
        absent = str(uuid.uuid4())
        with owner_io(native), installation_lock(self.keep.root/'installation.lock'), \
             patch.object(shutil.rmtree, 'avoids_symlink_attacks', False), \
             patch('installation_retention.os.walk', side_effect=AssertionError('No native Python scan')):
            for identifier in (existing, absent):
                self.assertEqual(self.keep.safe_path('stage', identifier), self.keep.path('stage', identifier))
        self.assertFalse(any(call[0] == 'remove' for call in peer.calls))
        self.assertFalse(self.keep.path('stage', absent).exists())

    def test_failed_unreferenced_build_has_identity_intent_before_one_remove(self):
        plan = self.stage(); identifier = Path(plan['stage']).name
        self.keep.mark('stage', identifier, state='failed')
        peer, native = self.native()
        with owner_io(native), installation_lock(self.keep.root/'installation.lock'):
            result = self.provider.cleanup(failed=identifier)
        self.assertEqual(result, {'pruned':['stage/'+identifier]})
        self.assertFalse(Path(plan['stage']).exists())
        self.assertEqual(self.keep.owned('stage', identifier)['state'], 'pruned')
        self.assertEqual(sum(c[0] == 'remove' for c in peer.calls), 1)

    def test_reference_guard_precedes_native_deletion(self):
        plan = self.stage(); identifier = Path(plan['stage']).name
        self.keep.mark('stage', identifier, state='failed')
        self.retain({'id':str(uuid.uuid4()),'component':'minecraft','plan':plan})
        peer, native = self.native()
        with owner_io(native), installation_lock(self.keep.root/'installation.lock'):
            self.assertEqual(self.provider.cleanup(failed=identifier), {'pruned':[]})
        self.assertFalse(any(c[0] == 'remove' for c in peer.calls))
        self.assertTrue(Path(plan['stage']).exists())

    def test_lost_remove_reply_unwinds_without_cleanup_write_or_redispatch(self):
        for removed in (False, True):
            with self.subTest(already_removed=removed):
                identifier = str(uuid.uuid4()); path = self.keep.path('stage', identifier)
                path.mkdir(parents=True); (path/'partial').write_text('preserve uncertainty')
                self.keep.mark('stage', identifier, state='failed')
                peer, native = self.native(); peer.unknown = True
                if removed:
                    peer.on_remove = lambda: shutil.rmtree(path)
                with owner_io(native), installation_lock(self.keep.root/'installation.lock'):
                    with self.assertRaises(LostReply):
                        self.keep.remove('stage', identifier, 'failed_build_unreferenced')
                self.assertFalse(peer.locked)
                record = self.keep.owned('stage', identifier)
                self.assertEqual(record['state'], 'pruning')
                self.assertIsNotNone(record['expected_tree'])
                self.assertEqual(sum(c[0] == 'remove' for c in peer.calls), 1)
                fresh, io = self.native()
                with owner_io(io), installation_lock(self.keep.root/'installation.lock'):
                    # Read-only reconciliation may observe absence, but null
                    # does not bind the old profile/root. Retain uncertainty.
                    io.tree_inspect('stage', identifier)
                    with self.assertRaises(ContinuityError):
                        self.keep.remove('stage', identifier, 'do not repeat')
                    self.assertIn('held', self.provider.cleanup())
                self.assertFalse(any(c[0] == 'remove' for c in fresh.calls))
                self.assertEqual(self.keep.owned('stage', identifier), record)

    def test_capability_and_explicit_owner_scope_required_without_fallback(self):
        peer, native = self.native(); identifier = str(uuid.uuid4())
        with self.assertRaises(ContinuityError):self.keep.safe_path('stage', identifier)
        for advertised in (None, 0, 2, True):
            peer.advertised = advertised
            with owner_io(native), self.assertRaises(ContinuityError):
                self.keep.safe_path('stage', identifier)
        self.assertFalse(any(c[0] == 'inspect' for c in peer.calls))

    def test_inspection_transport_failure_has_no_intent_or_cleanup_write(self):
        plan = self.stage(); identifier = Path(plan['stage']).name
        before = self.keep.owned('stage', identifier)
        peer, native = self.native(); failure = LostReply('read transport_timeout')
        with owner_io(native), installation_lock(self.keep.root/'installation.lock'), \
             patch.object(peer, 'tree_inspect', side_effect=failure):
            with self.assertRaises(LostReply) as caught:
                self.keep.remove('stage', identifier, 'no dispatch')
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.keep.owned('stage', identifier), before)
        self.assertEqual(peer.calls, [])

    def test_replaced_identity_refuses_with_original_intent_retained(self):
        plan = self.stage(); identifier = Path(plan['stage']).name
        peer, native = self.native(); path = Path(plan['stage'])
        retained = path.with_name('retained-fixture')
        def replace():
            path.rename(retained); path.mkdir(); (path/'new-user-data').write_text('keep')
        peer.on_remove = replace
        with owner_io(native), installation_lock(self.keep.root/'installation.lock'):
            with self.assertRaisesRegex(ContinuityError, 'Replaced tree'):
                self.keep.remove('stage', identifier, 'identity race')
        self.assertTrue(retained.exists())
        self.assertEqual((path/'new-user-data').read_text(), 'keep')
        self.assertEqual(self.keep.owned('stage', identifier)['state'], 'pruning')

    def test_mapping_rejects_wrong_root_subtree_or_lock(self):
        self.native()
        base = {'version':1,'roots':{k:self.cfg[k] for k in ('home','state')},
                'locks':{'installation':str(self.keep.root/'installation.lock')},
                'services':{'body':{},'controller':{}},
                'regenerable_trees':{n:{'root':'state','path':n,'lock':'installation'}
                                     for n in ('stages','backups')}}
        path = self.root/'driver.json'; path.write_text(json.dumps(base))
        validate_driver_mapping(self.cfg, path)
        for key in ('root','path','lock'):
            bad = copy.deepcopy(base); bad['regenerable_trees']['stages'][key] = 'other'
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):validate_driver_mapping(self.cfg, path)

    def test_cleanup_timeout_fits_remaining_invocation_without_changing_session(self):
        peer, _ = self.native()
        native = NativeIO(self.cfg, peer, cleanup_deadline=600)
        expected = {'opaque':'identity'}
        with patch('installation_native.time.monotonic',return_value=0):
            self.assertEqual(native.tree_removal_timeout(),120)
        with patch('installation_native.time.monotonic',return_value=450):
            self.assertEqual(native.tree_removal_timeout(),90)
        with patch('installation_native.time.monotonic',return_value=511):
            with self.assertRaises(ContinuityError):native.tree_removal_timeout()
        with patch.object(peer,'tree_remove',return_value={'absent':True}) as remove, \
             patch('installation_native.time.monotonic',return_value=470):
            native.tree_remove('stage',str(uuid.uuid4()),expected,timeout=90)
            self.assertEqual(remove.call_args.kwargs,{'timeout':70})
        self.assertIsNone(NativeIO(self.cfg,peer).tree_removal_timeout())

    def test_exhausted_cleanup_budget_does_not_write_intent_or_dispatch(self):
        plan = self.stage(); identifier = Path(plan['stage']).name
        before = self.keep.owned('stage',identifier)
        peer, _ = self.native(); native = NativeIO(self.cfg,peer,cleanup_deadline=600)
        with owner_io(native),installation_lock(self.keep.root/'installation.lock'), \
             patch('installation_native.time.monotonic',return_value=520):
            with self.assertRaisesRegex(ContinuityError,'Insufficient provider time'):
                self.keep.remove('stage',identifier,'defer')
        self.assertEqual(self.keep.owned('stage',identifier),before)
        self.assertFalse(any(c[0] in ('remove','write') for c in peer.calls))


del _Fixture
if __name__ == '__main__':unittest.main()
