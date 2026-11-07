"""Saved connections accept only the body's real status-only deadline expiry."""
import copy
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from installation_guard import ContinuityError, continuity, durable_write, read
from installation_connection import stored_continuity
import test_installation_connection as connections


class ExpiryTests(unittest.TestCase):
    # Reuse only the disposable lifecycle fixture, not its test cases.
    setUp = connections.ConnectionTests.setUp
    op = connections.ConnectionTests.op
    ack = connections.ConnectionTests.ack
    disconnect = connections.ConnectionTests.disconnect
    connect_ready = connections.ConnectionTests.connect_ready
    connect_settle = connections.ConnectionTests.connect_settle
    def finite_task(self, tagged=False, status='waiting'):
        task = {'id':'original', 'request_id':'human-source', 'requested_by':'human',
                'status':status, 'turns':8, 'max_turns':12, 'deadline':2000,
                'progress':[{'summary':'retained'}], 'recovery_attempts':2,
                'wait_for':{'id':'original-watch'}, 'unknown_effect':'unreplayed'}
        if tagged:
            task['bounds']={'version':1, 'deadline_ms':{'kind':'finite','value':2000},
                            'max_turns':{'kind':'finite','value':12}}
        self.store_task(task)
        return task

    def store_task(self, task):
        history=read(self.home/'workshop.json');history['task']=copy.deepcopy(task)
        durable_write(self.home/'workshop.json',history)
        self.backend.body['task']=copy.deepcopy(task)

    def body_expire(self, now=3000):
        subprocess.run(['node','-e',
            'Date.now=()=>Number(process.argv[2]); const {WorkshopState}=require("./workshop-state.cjs");'
            'new WorkshopState(process.argv[1]).task();',str(self.home/'workshop.json'),str(now)],
            cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True)
        self.backend.body['task']=read(self.home/'workshop.json')['task']

    def test_real_body_status_only_expiry_for_legacy_and_tagged_bounds(self):
        for tagged in (False,True):
            for status in ('running','waiting','review','blocked','needs_review'):
                with self.subTest(tagged=tagged,status=status):
                    original=self.finite_task(tagged,status)
                    with patch('installation_guard.time.time_ns',return_value=1000_000_000):
                        before=self.backend.capture()
                    self.body_expire()
                    after=self.backend.capture()
                    self.assertEqual(read(self.home/'workshop.json')['task'],
                                     {**original,'status':'budget_exhausted'})
                    self.assertTrue(stored_continuity(before,after)['finite_deadline_expiry'])
                    self.assertTrue(continuity(before,after,body_restart=True,
                                              allow_expiry=True)['finite_deadline_expiry'])
                    # Scheduled updater continuity has not silently gained this exception.
                    with self.assertRaises(ContinuityError):continuity(before,after,body_restart=True)
                    with self.assertRaises(ContinuityError):stored_continuity(after,before)

    def test_no_other_task_or_authority_drift_is_normalized(self):
        self.finite_task(True);before=self.backend.capture();self.body_expire()
        closed=read(self.home/'workshop.json')
        for field,value in [('id','replacement'),('deadline',4000),('turns',7),
                            ('max_turns',20),('progress',[]),('recovery_attempts',0),
                            ('wait_for',None),('request_id','new-source'),
                            ('unknown_effect','cleared'),('status','completed')]:
            with self.subTest(field=field):
                changed=copy.deepcopy(closed['task']);changed[field]=value;self.store_task(changed)
                with self.assertRaises(ContinuityError):stored_continuity(before,self.backend.capture())
        durable_write(self.home/'workshop.json',closed);self.backend.body['task']=closed['task']
        changed=copy.deepcopy(closed);changed['unknown_receipts']=[]
        durable_write(self.home/'workshop.json',changed)
        with self.assertRaises(ContinuityError):stored_continuity(before,self.backend.capture())

    def test_exact_original_deadline_and_captured_evidence_required(self):
        self.finite_task();before=self.backend.capture();self.body_expire(now=2000)
        with patch('installation_guard.time.time_ns',return_value=1999_000_000):
            with self.assertRaises(ContinuityError):stored_continuity(before,self.backend.capture())
        with patch('installation_guard.time.time_ns',return_value=2000_000_000):
            after=self.backend.capture()
        self.assertTrue(stored_continuity(before,after)['finite_deadline_expiry'])
        before.pop('expiry_projection')
        with self.assertRaises(ContinuityError):stored_continuity(before,after)

    def test_early_unknown_unbounded_or_contradictory_expiry_rejected(self):
        for change in ({'deadline':None}, {'turns':True}, {'max_turns':None},
                       {'deadline':9999999999999},
                       {'bounds':{'version':1,'deadline_ms':{'kind':'no_configured_bound'},
                                  'max_turns':{'kind':'finite','value':12}}},
                       {'bounds':{'version':1,'deadline_ms':{'kind':'finite','value':2001},
                                  'max_turns':{'kind':'finite','value':12}}}):
            with self.subTest(change=change):
                task=self.finite_task();task.update(change);self.store_task(task)
                before=self.backend.capture()
                self.store_task({**task,'status':'budget_exhausted'})
                with self.assertRaises(ContinuityError):stored_continuity(before,self.backend.capture())

    def test_disconnect_restart_expiry_load_and_lost_terminal_reply(self):
        original=self.finite_task(True)
        session=(self.home/'session.json').read_bytes()
        self.disconnect()
        actions=self.backend.action
        def start(kind,action):
            actions(kind,action)
            if (kind,action)==('body','start'):self.body_expire()
        self.backend.action=start
        result=self.connect_settle()
        self.assertTrue(result['settled']);self.assertEqual(result['state'],'connected')
        journal=read(self.root/'owner/connections'/(self.id+'.json'))
        self.assertTrue(journal['checks']['finite_deadline_expiry'])
        self.assertEqual(read(self.home/'workshop.json')['task'],{**original,'status':'budget_exhausted'})
        effects=list(self.backend.actions)
        self.assertEqual(self.op().run(),result)
        self.assertEqual(self.backend.actions,effects)
        self.assertEqual(sum(a==('session','start-original-only') for a in effects),1)
        self.assertEqual((self.home/'session.json').read_bytes(),session)
        self.assertEqual(read(self.home/'workshop.json')['unknown_receipts'],['unreplayed'])
        # A later disconnect/reconnect uses the actual exhausted state, never reopens it.
        self.id=str(uuid.uuid4());self.disconnect();self.connect_settle()
        self.assertEqual(read(self.home/'workshop.json')['task'],{**original,'status':'budget_exhausted'})
