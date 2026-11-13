"""Explicit journal routing and actual opt-in driver composition; no services."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from installation_guard import ContinuityError, durable_write, owner_io, read, read_bytes
from installation_native import NativeIO


class Peer:
    def __init__(self):
        self.calls = []
        self.data = b'{"phase":"original"}'
        self.error = None
        self.description = {'private_data_read':1, 'private_data_publication':1,
                            'operations':['storage.read_data','storage.write_data']}
    def describe(self):
        return copy.deepcopy(self.description)
    def private_read_data(self, *args, **kwargs):
        self.calls.append(('read', args, kwargs))
        if self.error:
            raise self.error
        return self.data
    def private_write_data(self, *args):
        self.calls.append(('data_write', args))
    def private_write(self, *args):
        self.calls.append(('strict_write', args))
    def private_dir(self, *args):
        self.calls.append(('mkdir', args))


class NativeDataJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.cfg = {'home':str(self.base/'home'), 'state':str(self.base/'state'),
                    'native_platform':{'data_journals':1}}
        self.peer = Peer()
        self.io = NativeIO(self.cfg, self.peer)
        self.path = self.base/'state/transactions/original.json'

    def test_selected_mutable_journals_use_paired_reader_writer(self):
        paths = ['state/transactions/a.json','state/connections/a.json',
                 'state/provider-receipts/a.json','state/native-source-receipts/a.json',
                 'state/artifact-receipts/a.json','state/active.json','state/cleanup-last.json',
                 'home/app-source.json','home/installation-updates/gate.json',
                 'home/installation-updates/controller-idle.json',
                 'home/installation-connections/state.json']
        with owner_io(self.io):
            for relative in paths:
                with self.subTest(path=relative):
                    path = self.base/relative
                    self.assertEqual(read(path), {'phase':'original'})
                    durable_write(path, {'phase':'next'})
        self.assertEqual(sum(c[0]=='read' for c in self.peer.calls),len(paths))
        self.assertEqual(sum(c[0]=='data_write' for c in self.peer.calls),len(paths))
        self.assertFalse(any(c[0]=='strict_write' for c in self.peer.calls))

    def test_history_packages_owner_config_and_external_plans_are_separate(self):
        paths = ['home/workshop.json','home/config.json','home/session.json',
                 'state/driver.json','state/stages/a/manifest.json',
                 'state/stages/a/package-receipt.json','shared/plans/a/plan.json']
        with owner_io(self.io):
            for relative in paths:
                path = self.base/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"original":true}')
                self.assertEqual(read(path), {'original':True})
                if not relative.startswith('shared/'):
                    durable_write(path, {'unchanged_strict_route':True})
        self.assertFalse(any(c[0] in ('read','data_write') for c in self.peer.calls))
        self.assertEqual(sum(c[0]=='strict_write' for c in self.peer.calls),len(paths)-1)

    def test_absent_empty_invalid_and_refused_are_distinct(self):
        with owner_io(self.io):
            self.peer.data = None
            with self.assertRaises(FileNotFoundError):read(self.path)
            self.peer.data = b''
            self.assertEqual(read_bytes(self.path), b'')
            with self.assertRaises(json.JSONDecodeError):read(self.path)
            self.peer.data = b'{bad'
            with self.assertRaises(json.JSONDecodeError):read(self.path)
            error = RuntimeError('permission denied or transport loss')
            self.peer.error = error
            with self.assertRaises(RuntimeError) as caught:read(self.path)
            self.assertIs(caught.exception,error)
        self.assertFalse(any(c[0].endswith('write') for c in self.peer.calls))

    def test_read_never_falls_back_after_native_error(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"apparently_valid":true}')
        self.peer.error = RuntimeError('oversize')
        with owner_io(self.io), self.assertRaisesRegex(RuntimeError,'oversize'):
            read(self.path)
        self.assertEqual(len(self.peer.calls),1)

    def test_missing_parent_is_not_repaired_during_read(self):
        self.peer.error=RuntimeError('missing protected parent')
        with owner_io(self.io),self.assertRaisesRegex(RuntimeError,'missing protected parent'):
            read(self.path,default={})
        self.assertEqual([c[0] for c in self.peer.calls],['read'])
        self.assertFalse(self.path.parent.exists())

    def test_oversize_write_refuses_before_directory_or_publication(self):
        with owner_io(self.io), self.assertRaisesRegex(ContinuityError,'1 MiB'):
            durable_write(self.path, {'data':'x'*1048576})
        self.assertEqual(self.peer.calls,[])

    def test_both_exact_capabilities_and_operations_required_before_io(self):
        for key in ('private_data_read','private_data_publication'):
            for bad in (None,True,2,'1'):
                peer=Peer();peer.description[key]=bad
                with self.subTest(key=key,value=bad),self.assertRaises(ContinuityError):
                    NativeIO(self.cfg,peer)
                self.assertEqual(peer.calls,[])
        for operation in self.peer.description['operations']:
            peer=Peer();peer.description['operations'].remove(operation)
            with self.assertRaises(ContinuityError):NativeIO(self.cfg,peer)
        for bad in (False,True,0,'1'):
            cfg=copy.deepcopy(self.cfg);cfg['native_platform']['data_journals']=bad
            with self.assertRaises(ValueError):NativeIO(cfg,Peer())

    def test_not_enrolled_keeps_previous_strict_route(self):
        cfg=copy.deepcopy(self.cfg);cfg['native_platform']={}
        peer=Peer();peer.description={}
        self.path.parent.mkdir(parents=True);self.path.write_text('{"old":true}')
        with owner_io(NativeIO(cfg,peer)):
            self.assertEqual(read(self.path),{'old':True})
            durable_write(self.path,{'next':True})
        self.assertEqual([c[0] for c in peer.calls],['mkdir','strict_write'])

    def test_reference_hash_and_parse_use_one_identical_snapshot(self):
        from installation_retention import Retention
        import hashlib
        shared=self.base/'shared';plans=shared/'plans';plans.mkdir(parents=True)
        first=b'{"state":"succeeded","transaction":null}'
        cfg={**self.cfg,'shared_plans':str(plans),'app':str(self.base/'home/app'),
             'venv':str(self.base/'home/venv')}
        for p in (self.base/'state',self.base/'home/app',self.base/'home/venv'):
            p.mkdir(parents=True,exist_ok=True)
        (shared/'state.json').write_bytes(first)
        with patch('installation_retention.read_bytes',return_value=first) as reader:
            _,_,signature=Retention(cfg).references()
        self.assertEqual(reader.call_count,1)
        self.assertEqual(signature[str(shared/'state.json')],hashlib.sha256(first).hexdigest())


@unittest.skipUnless(os.environ.get('MINECRAFT_DATA_DRIVER'), 'explicit frozen driver required')
class ActualDataJournalTests(unittest.TestCase):
    def setUp(self):
        from constellation_native import initialize_root,initialize_config
        self.tmp=tempfile.TemporaryDirectory(prefix='minecraft-data-journals-')
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.driver=Path(os.environ['MINECRAFT_DATA_DRIVER']).resolve()
        self.home=self.base/'home';self.state=self.base/'state'
        for p in (self.home,self.state):initialize_root(self.driver,p)
        self.config=self.state/'driver.json'
        initialize_config(self.driver,self.config,{'version':1,
            'roots':{'home':str(self.home),'state':str(self.state)},
            'locks':{'installation':str(self.state/'installation.lock')}})
        self.cfg={'home':str(self.home),'state':str(self.state),'native_platform':{'data_journals':1}}
        self.path=self.state/'transactions/original.json'

    def test_separate_actual_sessions_publish_and_read_complete_journals(self):
        from constellation_native import Session
        with Session(self.driver,self.config) as writer,Session(self.driver,self.config) as reader:
            w=NativeIO(self.cfg,writer);r=NativeIO(self.cfg,reader)
            with writer.lock('installation'):
                for number in range(12):
                    value={'transaction_id':'original','phase':number,'retained':'x'*4096}
                    with owner_io(w):durable_write(self.path,value)
                    with owner_io(r):self.assertEqual(read(self.path),value)
                with owner_io(r):
                    with self.assertRaises(FileNotFoundError):read(self.state/'transactions/missing.json')
                writer.private_write_data('state','transactions/empty.json',b'')
                with owner_io(r):
                    self.assertEqual(read_bytes(self.state/'transactions/empty.json'),b'')
                    with self.assertRaises(json.JSONDecodeError):read(self.state/'transactions/empty.json')

    def test_lost_committed_ack_unwinds_then_readonly_reconciles_without_replay(self):
        from constellation_native import Session,Unknown
        from installation_guard import installation_lock
        from installation_retention import Retention
        identifier='c560aeef-9078-4f7a-a2fa-a7a614dc4adb'
        class LostAck(Session):
            dispatches=0
            def private_write_data(self,*args,**kwargs):
                result=super().private_write_data(*args,**kwargs)
                type(self).dispatches+=1
                self.close()
                raise Unknown('transport_timeout','simulated lost acknowledgment after actual publication')
        class Recovery(Session):
            def private_write_data(self,*args,**kwargs):
                raise AssertionError('Recovery must not republish')
            def private_write(self,*args,**kwargs):
                raise AssertionError('Recovery must not use strict publication either')
        keep=Retention(self.cfg)
        value={'version':1,'kind':'stage','id':identifier,'home':str(self.home),
               'root':str(self.state),'state':'pruning','unknown':'preserved'}
        with LostAck(self.driver,self.config) as session:
            with self.assertRaises(Unknown):
                with owner_io(NativeIO(self.cfg,session)),installation_lock(self.state/'installation.lock'):
                    keep.mark('stage',identifier,state='pruning',unknown='preserved')
        with Recovery(self.driver,self.config) as session:
            with owner_io(NativeIO(self.cfg,session)),installation_lock(self.state/'installation.lock'):
                self.assertEqual(keep.owned('stage',identifier),value)
        self.assertEqual(LostAck.dispatches,1)


if __name__=='__main__':unittest.main()
