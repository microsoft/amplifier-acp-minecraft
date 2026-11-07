import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from installation_guard import ContinuityError, NotIdle, durable_write, read, snapshot
from installation_participant import Participant
from update_admission import held


class FakeInstallation:
    def __init__(self, home):
        self.home, self.actions = home, []
        self.units = {k:{'ActiveState':'active', 'MainPID':str(pid), 'LoadState':'loaded',
                        'UnitFileState':'enabled', 'unit_sha256':'same',
                        'ExecMainStartTimestamp':'original',
                        'process_identity':{'pid':pid,'start_ticks':'10','boot_id':'boot'}}
                      for k,pid in [('controller',100),('body',101)]}
        self.body = {'task':{'id':'preserved','status':'budget_exhausted','turns':8},
                     'ready':True,'busy':False,'turn_active':False,
                     'action_lease':{'version':1,'lease_id':None,'expires_at':0,'renewable':False},
                     'inventory':{'slots':[{'name':'pickaxe','damage':48}], 'cursor':None},
                     'position':{'x':1,'y':64,'z':3}}
        durable_write(home/'workshop.json', {'task':self.body['task'], 'turn':None,
                                            'unknown_receipts':['unreplayed'], 'inbox':[]})
        durable_write(home/'session.json', {'id':'original-session'})
    def services(self): return copy.deepcopy(self.units)
    def capture(self):
        live = self.body if self.units['body']['ActiveState']=='active' else None
        return snapshot(self.home, self.services(), live, {**live,'action_sequence':None} if live else None)
    def action(self,kind,action):
        self.actions.append((kind,action))
        if action=='stop': self.units[kind].update(ActiveState='inactive',MainPID='0')
        else: self.units[kind].update(ActiveState='active',MainPID='200',ExecMainStartTimestamp='new')
    def helper(self): return {'capabilities':'static-only'}
    def session(self, timeout):
        self.actions.append(('session','load-only'))
        return {'verified':True,'saved_session_loaded':True,'new_session_created':False,'prompt_sent':False}


class ParticipantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'game';self.home.mkdir()
        self.cfg={'home':str(self.home),'state':str(Path(self.tmp.name)/'owner-state')}
        self.envelope={'id':str(uuid.uuid4()),'participant':'minecraft','plan':{
            'schema':1,'transaction_id':str(uuid.uuid4()),'operation':'apply',
            'components':['instance'],'restart_scope':{'services':[],'instance':True,'slack_homes':[]}}}
        self.backend=FakeInstallation(self.home)
    def participant(self): return Participant(self.cfg,self.envelope,self.backend)
    def ack(self):
        durable_write(self.home/'installation-updates/controller-idle.json',{
            'transaction_id':self.envelope['plan']['transaction_id'],
            **self.backend.units['controller']['process_identity']})
    def ready(self):
        p=self.participant();self.assertFalse(p.prepare()['ready']);self.ack()
        for _ in range(5):
            if p.prepare()['ready']: return p
        self.fail('never ready')
    def test_second_connection_only_responds_to_its_own_source_component(self):
        self.cfg.update(participant_id='minecraft-visit', component_ids={'minecraft':'minecraft-visit','task-helpers':'task-helpers-visit'})
        self.envelope['participant']='minecraft-visit'
        self.envelope['plan']['components']=['minecraft']
        p=self.participant();self.assertTrue(p.prepare()['ready']);self.assertEqual(self.backend.actions,[])
        self.envelope['plan']['components']=['minecraft-visit']
        p=self.ready();self.assertEqual(self.backend.actions,[('controller','stop'),('body','stop')])
        p.verify('applied');p.restore('applied')
        self.assertEqual(read(self.home/'session.json'),{'id':'original-session'})

    def test_wrong_participant_and_shared_role_collisions_rejected(self):
        self.cfg['participant_id']='minecraft-visit'
        with self.assertRaises(ValueError):self.participant()
        self.envelope['participant']='minecraft-visit'
        for ids in [{'minecraft':'instance','task-helpers':'task-helpers-visit'},
                    {'minecraft':'same','task-helpers':'same'},
                    {'minecraft':'../other','task-helpers':'valid'}]:
            self.cfg['component_ids']=ids
            with self.assertRaises(ValueError):self.participant()
        self.assertEqual(self.backend.actions,[])

    def test_shared_only_keeps_body_and_never_renews_or_replays(self):
        before=(self.home/'workshop.json').read_bytes();p=self.ready()
        self.assertEqual(self.backend.actions,[('controller','stop')])
        self.assertTrue(p.verify('applied')['verified']);self.assertTrue(p.restore('applied')['restored'])
        self.assertEqual(self.backend.actions,[('controller','stop'),('session','load-only'),('controller','start')])
        self.assertEqual((self.home/'workshop.json').read_bytes(),before)
    def test_game_update_stops_body_then_verifies_before_opening_admission(self):
        self.envelope['plan']['components']=['minecraft'];p=self.ready()
        self.assertEqual(self.backend.actions,[('controller','stop'),('body','stop')])
        p.verify('applied');self.assertTrue(held(self.home))
        self.assertEqual(self.backend.actions[-2:],[('body','start'),('session','load-only')])
        p.restore('applied');self.assertFalse(held(self.home))
        self.assertEqual(self.backend.actions[-1],('controller','start'))
    def test_recent_engagement_defers_before_gate_and_later_uses_same_transaction(self):
        self.backend.body['human_engagement']={'version':1,'active':True}
        p=self.participant();before=(self.home/'workshop.json').read_bytes()
        self.assertEqual(p.prepare(),{'ready':False,'reason':'recent_human_engagement'})
        self.assertFalse(p.gate.exists());self.assertFalse(p.path.exists());self.assertEqual(self.backend.actions,[])
        self.assertEqual((self.home/'workshop.json').read_bytes(),before)
        self.backend.body['human_engagement']['active']=False
        p=self.ready();self.assertTrue(p.prepare()['ready'])
        # Once gated, fresh observations do not strand an already admitted update.
        self.backend.body['human_engagement']['active']=True
        p.verify('applied');p.restore('applied');self.assertFalse(p.gate.exists())

    def test_busy_prepare_closes_admission_without_interrupting_work(self):
        p=self.participant();p.prepare();self.ack();self.backend.body['busy']=True
        self.assertFalse(p.prepare()['ready']);self.assertEqual(self.backend.actions,[])
        p.verify('unchanged');p.restore('unchanged');self.assertFalse(held(self.home))
        self.assertTrue(self.backend.body['busy'])
    def test_ack_must_match_current_process_and_transaction(self):
        p=self.participant();p.prepare();self.ack()
        ack=self.home/'installation-updates/controller-idle.json';v=read(ack);v['start_ticks']='old';durable_write(ack,v)
        self.assertFalse(p.prepare()['ready']);self.assertEqual(self.backend.actions,[])
    def test_paused_or_masked_installation_stays_paused(self):
        for unit in self.backend.units.values():
            unit.update(ActiveState='inactive',MainPID='0',LoadState='masked',UnitFileState='masked')
        p=self.participant();self.assertTrue(p.prepare()['ready'])
        p.verify('applied');p.restore('applied');self.assertEqual(self.backend.actions,[('session','load-only')])
    def test_repeated_prepare_does_not_recapture_or_repeat_stop(self):
        p=self.ready();baseline=copy.deepcopy(p.value['baseline']);actions=list(self.backend.actions)
        p=self.participant();self.assertTrue(p.prepare()['ready'])
        self.assertEqual(p.value['baseline'],baseline);self.assertEqual(self.backend.actions,actions)
    def test_changed_accounting_fails_closed_without_restoring_old_state(self):
        p=self.ready();durable_write(self.home/'session.json',{'id':'unexpected'})
        with self.assertRaises(ContinuityError): p.verify('applied')
        self.assertTrue(held(self.home));self.assertEqual(read(self.home/'session.json')['id'],'unexpected')
        with self.assertRaises(ContinuityError): p.restore('applied')
    def test_external_mask_wins_over_restore(self):
        p=self.ready();p.verify('applied');self.backend.units['controller']['LoadState']='masked'
        with self.assertRaises(ContinuityError): p.restore('applied')
        self.assertTrue(held(self.home))
    def test_active_but_already_masked_unit_is_not_interrupted(self):
        self.backend.units['controller']['LoadState']='masked'
        with self.assertRaises(NotIdle):self.participant().prepare()
        self.assertFalse(held(self.home));self.assertEqual(self.backend.actions,[])
    def test_lost_restore_reply_never_rolls_back_or_rechecks_resumed_authority(self):
        p=self.ready();p.verify('applied');p.restore('applied')
        actions=list(self.backend.actions);durable_write(self.home/'session.json',{'id':'new-real-input'})
        retry=self.participant();self.assertTrue(retry.verify('applied')['verified'])
        self.assertTrue(retry.restore('applied')['restored']);self.assertEqual(self.backend.actions,actions)
    def test_context_config_and_outcome_changes_are_rejected(self):
        p=self.ready();self.cfg['unexpected']='change'
        with self.assertRaises(ContinuityError):self.participant()
        del self.cfg['unexpected'];p.verify('applied')
        with self.assertRaises(ContinuityError):p.restore('rolled_back')
        self.envelope['plan']['components']=['minecraft']
        with self.assertRaises(ContinuityError):self.participant()
    def test_unknown_component_does_not_touch_game(self):
        self.envelope['plan']['components']=['unrelated'];p=self.participant()
        self.assertTrue(p.prepare()['ready']);self.assertTrue(p.verify('applied')['verified'])
        self.assertTrue(p.restore('applied')['restored']);self.assertEqual(self.backend.actions,[])
    def test_other_transaction_cannot_take_an_uncertain_hold(self):
        self.ready();self.envelope['plan']['transaction_id']=str(uuid.uuid4())
        with self.assertRaises(ContinuityError):self.participant().prepare()
    def test_failure_before_stop_can_release_only_its_unchanged_gate(self):
        from unittest.mock import patch
        p=self.participant();p.prepare();self.ack()
        with patch.object(self.backend,'action',side_effect=OSError('stop not issued')):
            with self.assertRaises(OSError):p.prepare()
        p=self.participant();p.verify('unchanged');p.restore('unchanged')
        self.assertFalse(held(self.home));self.assertEqual(self.backend.actions,[])
    def test_human_input_arriving_while_paused_survives_restoration(self):
        p=self.ready();state=read(self.home/'workshop.json')
        state['inbox'].append({'id':'new-human-input','source':'human','message':'hello'})
        durable_write(self.home/'workshop.json',state)
        p.verify('applied');p.restore('applied')
        self.assertEqual(read(self.home/'workshop.json')['inbox'],state['inbox'])

    def test_engine_update_checks_original_session_and_failure_keeps_listener_closed(self):
        from unittest.mock import patch
        self.envelope['plan']['components']=['engine'];p=self.ready()
        with patch.object(self.backend,'session',side_effect=RuntimeError('incompatible old session')):
            with self.assertRaises(RuntimeError):p.verify('applied')
        self.assertTrue(held(self.home))
        self.assertEqual(self.backend.units['controller']['ActiveState'],'inactive')
        self.assertNotEqual(p.value['phase'],'verified')
        # Old engine restored by worker: verify the same binding before resuming.
        p.verify('rolled_back');p.restore('rolled_back')
        self.assertEqual(p.value['session']['saved_session_loaded'],True)

    def test_helper_only_and_unchanged_busy_failure_do_not_load_session(self):
        self.envelope['plan']['components']=['task-helpers'];p=self.ready()
        p.verify('applied');p.restore('applied')
        self.assertNotIn(('session','load-only'),self.backend.actions)

    def test_session_load_cannot_mutate_authority_and_call_it_verified(self):
        from unittest.mock import patch
        p=self.ready()
        def load(timeout):
            durable_write(self.home/'session.json',{'id':'replacement'})
            return {'verified':True,'saved_session_loaded':True}
        with patch.object(self.backend,'session',side_effect=load):
            with self.assertRaises(ContinuityError):p.verify('applied')
        self.assertTrue(held(self.home));self.assertNotEqual(p.value['phase'],'verified')

    def test_explicit_long_verification_budget_does_not_change_task_authority(self):
        from unittest.mock import patch
        self.cfg['session_verification_seconds']=180
        p=self.ready();before=read(self.home/'workshop.json')
        with patch.object(self.backend,'session',wraps=self.backend.session) as session:
            p.verify('applied')
        self.assertGreater(session.call_args.kwargs['timeout'],180)
        self.assertLessEqual(session.call_args.kwargs['timeout'],186)
        self.assertEqual(read(self.home/'workshop.json'),before)
        self.assertTrue(held(self.home))
        p.restore('applied')
        self.assertFalse(held(self.home))

if __name__=='__main__': unittest.main()
