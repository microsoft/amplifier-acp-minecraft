import unittest
from ops.observe_run import signals

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
