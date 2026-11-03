import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
from analyze_experiment import analyze


class ExperimentReportTests(unittest.TestCase):
    def test_evicted_events_survive_and_overlapping_receipts_count_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root/'player';home.mkdir();observations=root/'observations';observations.mkdir()
            events=[{'id':str(i),'time':f'2026-01-01T00:00:0{i}Z','kind':'action_result','action':'build','result':{}} for i in range(3)]
            (home/'workshop.json').write_text(json.dumps({'events':events[-1:],'task':{}}))
            (observations/'player-events.jsonl').write_text('\n'.join(map(json.dumps,events[:2]))+'\n'+json.dumps(events[1])+'\n{"incomplete":')
            result=analyze(root,'2026-01-01T00:00:00Z',['player'],observations)['players']['player']
            self.assertEqual(result['tool_results'],3)
            self.assertEqual(result['event_coverage']['events'],3)
            self.assertEqual(result['event_coverage']['invalid_records'],1)
            self.assertEqual(result['event_coverage']['source'],'observer_and_recent_buffer')

    def test_buffer_only_reports_its_limit_and_excludes_prior_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root/'player';home.mkdir()
            (home/'workshop.json').write_text(json.dumps({'events':[{'id':'old','time':'2025-12-31T00:00:00Z','kind':'action_result'}],'task':{}}))
            result=analyze(root,'2026-01-01T00:00:00Z',['player'])['players']['player']
            self.assertEqual(result['tool_results'],0)
            self.assertEqual(result['event_coverage']['source'],'recent_buffer_only')
            self.assertIsNone(result['event_coverage']['earliest'])


if __name__=='__main__':unittest.main()
