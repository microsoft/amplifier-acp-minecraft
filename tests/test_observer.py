import unittest
from copy import deepcopy
from ops.observe_run import signals, task_evidence

class ObservationTests(unittest.TestCase):
    def test_waiting_is_not_a_stall_and_reports_are_not_verification(self):
        state={'ready':True,'task':{'status':'waiting','started_at':'2026-01-01T00:00:00Z'}}
        result=signals(state,{},1767226800000)
        self.assertEqual([x['code'] for x in result],['waiting'])
        state['task']['status']='review'
        self.assertIn('independent review',signals(state,{},1767226800000)[0]['text'])

    def test_interruption_and_long_turn_are_visible_without_retrying(self):
        state={'ready':False,'turn_active':True,'task':{'status':'needs_review'}}
        history={'turn':{'started_at':'2026-01-01T00:00:00Z'}}
        self.assertEqual({x['code'] for x in signals(state,history,1767226800000)}, {'disconnected','needs_review','long_turn'})
        self.assertEqual(state['task']['status'],'needs_review')

    def test_active_but_silent_is_distinct_from_finished(self):
        state={'ready':True,'task':{'status':'running','started_at':'2026-01-01T00:00:00Z'}}
        self.assertEqual(signals(state,{},1767226800000)[0]['code'],'no_recent_activity')
        state['task']['status']='stopped'
        self.assertEqual(signals(state,{},1767226800000),[])

    def test_expiry_preserves_delivery_evidence_without_reviving_authority(self):
        task={'id':'current','status':'budget_exhausted','turns':4,'deadline':2000}
        history={'events':[{'id':'receipt','kind':'work_status','task_id':'current',
                           'time':'1970-01-01T00:00:01Z','status':'review',
                           'progress':{'summary':'Ready for inspection.'}}]}
        original=deepcopy((task,history))
        out=task_evidence(task,history,3000)
        self.assertTrue(out['deadline_passed'])
        self.assertEqual(out['last_work_report']['status'],'review')
        self.assertEqual(out['last_work_report']['event_id'],'receipt')
        self.assertFalse(out['last_work_report']['independent_acceptance'])
        codes={s['code'] for s in signals({'ready':True,'task':task},history,3000)}
        self.assertEqual(codes,{'budget_exhausted','delivery_reported'})
        self.assertEqual((task,history),original)

    def test_latest_report_can_supersede_delivery_even_when_sequence_resets(self):
        task={'id':'current','status':'budget_exhausted','deadline':5000,
              'reviewed_at':'1970-01-01T00:00:01Z'}
        history={'events':[
            {'id':'old','seq':900,'kind':'work_status','task_id':'current','status':'review','time':'1970-01-01T00:00:01Z'},
            {'id':'new','seq':2,'kind':'work_status','task_id':'current','status':'running','time':'1970-01-01T00:00:02Z'},
            {'id':'foreign','seq':3,'kind':'work_status','task_id':'other','status':'review','time':'1970-01-01T00:00:03Z'}]}
        out=task_evidence(task,history,6000)
        self.assertEqual(out['last_work_report']['event_id'],'new')
        self.assertEqual(out['last_work_report']['status'],'running')
        self.assertNotIn('delivery_reported',{s['code'] for s in signals({'ready':True,'task':task},history,6000)})

    def test_review_timestamp_or_chat_prose_alone_is_not_a_delivery_receipt(self):
        task={'id':'current','status':'budget_exhausted','reviewed_at':'1970-01-01T00:00:01Z'}
        history={'events':[{'kind':'chat','task_id':'current','message':'Everything is done!'}]}
        self.assertIsNone(task_evidence(task,history,6000)['last_work_report'])
        self.assertIsNone(task_evidence(task,history,6000)['deadline_passed'])
