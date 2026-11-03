import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ops"))
from measure_attention import collect_journal, codex_reader, idle_intervals, journal_summary, native_reader


class UsageEvidence(unittest.TestCase):
    def test_native_counts_provider_requests_separately_from_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"history.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE events(seq INTEGER,session TEXT,turn TEXT,kind TEXT,at TEXT,data TEXT)")
                for seq,session,kind,value in [(1,"own","model.finished",{}),(2,"other","model.started",{}),
                        (3,"own","model.started",{"index":1}),(4,"own","model.finished",{"index":1,"usage":{"input_tokens":20,"input_tokens_details":{"cached_tokens":15},"output_tokens":3}}),
                        (5,"own","model.started",{"index":2})]:
                    db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",(seq,session,"same-turn",kind,"2026-01-01T00:00:00Z",json.dumps(value)))
            result=native_reader({"path":str(path),"session":"own","baseline_seq":1})
            self.assertEqual(result["requests_started"],2)
            self.assertEqual(result["responses_finished"],1)
            self.assertEqual(result["usage"]["input_tokens"],20)
            self.assertEqual(result["usage"]["cached_input_tokens"],15)

    def test_codex_duplicate_updates_and_partial_append_do_not_double_count(self):
        def line(total):
            return json.dumps({"type":"event_msg","timestamp":"2026-01-01T00:00:00Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":total,"cached_input_tokens":total-10,"output_tokens":5}}}}).encode()+b"\n"
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"usage.jsonl";path.write_bytes(line(110)+line(110)+line(130)[:17])
            spec={"path":str(path),"baseline_offset":0,"baseline_totals":{"input_tokens":100,"cached_input_tokens":90,"output_tokens":5}};cursor={}
            first=codex_reader(spec,cursor)
            self.assertIsNone(first["requests_started"])
            self.assertEqual(first["usage_updates_observed"],1)
            self.assertEqual(first["usage"]["input_tokens"],10)
            with path.open("ab") as out:out.write(line(130)[17:])
            second=codex_reader(spec,cursor)
            self.assertEqual(second["usage_updates_observed"],2)
            self.assertEqual(second["usage"]["input_tokens"],30)
            self.assertEqual(codex_reader(spec,cursor)["usage_updates_observed"],2)

    def test_counter_reset_does_not_create_negative_or_invented_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"usage.jsonl"
            path.write_text(json.dumps({"type":"event_msg","timestamp":"2026-01-01T00:00:00Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":5}}}})+"\n")
            spec={"path":str(path),"baseline_offset":0,"baseline_totals":{"input_tokens":100}}
            result=codex_reader(spec,{})
            self.assertEqual(result["counter_resets"],1)
            self.assertEqual(result["usage_updates_observed"],0)
            self.assertEqual(result["usage"],{})
            with self.assertRaises(ValueError):codex_reader(spec,{"offset":path.stat().st_size+1})


class AdmissionEvidence(unittest.TestCase):
    def test_filtering_events_are_not_avoided_requests_or_turn_admissions(self):
        rows=[{'time':1,'kind':'watch_filtered','events':19,'model_called':True},
              {'time':2,'kind':'watch_filtered','events':3,'model_called':False},
              {'time':3,'kind':'watch_filtered','events':2},
              {'time':4,'kind':'permission_context_supplied','active':True}]
        out=journal_summary(rows,10)
        self.assertEqual(out['counts']['metadata_filtered_events'],24)
        self.assertEqual(out['counts']['metadata_filter_batches_with_model_call'],1)
        self.assertEqual(out['counts']['metadata_filter_batches_without_model_call'],1)
        self.assertEqual(out['counts']['metadata_filter_batches_model_call_unknown'],1)
        self.assertEqual(out['counts']['permission_context_supplied'],1)
        self.assertEqual(out['planner_admissions'],[])
        self.assertNotIn('semantic_evaluations',out['counts'])

    def test_advice_is_not_a_gate_and_explicit_requests_keep_their_cause(self):
        rows=[{"time":1,"kind":"agent_assessment","phase":"running"},
              {"time":2,"kind":"turn_started","messages":[{"source":"human"}]},
              {"time":3,"kind":"watch_applied","application":"advisory"},
              {"time":4,"kind":"turn_started","messages":[{"source":"continuation"}]},
              {"time":5,"kind":"watch_applied","application":"wake"},
              {"time":6,"kind":"turn_started","messages":[{"source":"agent"}]},
              {"time":7,"kind":"assessment_applied","application":"wake"},
              {"time":8,"kind":"turn_started","messages":[{"source":"continuation"}]}]
        out=journal_summary(rows,10)
        self.assertEqual([r["reason"] for r in out["planner_admissions"]],["human_request","active_work_continuation","peer_request","waiting_assessment"])
        self.assertEqual(out["counts"]["active_turn_advisories"],1)

    def test_batched_hold_is_one_evaluation_and_budget_wait_is_separate(self):
        rows=[{"time":1,"kind":"watch_evaluated","elapsed_ms":10,"result":{"usage":{}},"receipts":[{"wake":False},{"wake":False}]},
              {"time":2,"kind":"watch_evaluated","evaluator":"predicate","receipts":[{"wake":True}]},
              {"time":3,"kind":"budget_wait"},{"time":8,"kind":"budget_resumed"},{"time":9,"kind":"budget_wait"}]
        out=journal_summary(rows,10)
        self.assertEqual(out["counts"]["semantic_hold_results"],1)
        self.assertEqual(out["counts"]["semantic_evaluations"],1)
        self.assertEqual(out["counts"]["exact_predicate_evaluations"],1)
        self.assertEqual(out["capacity_wait_seconds"],6)

    def test_idle_samples_exclude_admission_capacity_gaps_and_prior_task(self):
        def row(at,task="new",active=False):
            return {"at":at,"players":{"a":{"ready":True,"busy":False,"turn_active":active,"task":{"id":task,"status":"waiting"}}}}
        journal={"planner_admissions":[{"at":50}],"capacity_wait_spans":[[60,80]]}
        samples=[row(0,"old"),row(20,"old"),row(40),row(60),row(80),row(100),row(200),row(220,active=True)]
        model={"receipts":[{"at":90,"kind":"model.started"}]}
        out=idle_intervals(samples,"a",journal,model,"new")
        self.assertEqual(out["sampled_idle_seconds_by_state"],{"waiting":20})
        self.assertEqual(len(out["native_requests_inside_idle_intervals"]),1)


class JournalCoverage(unittest.TestCase):
    def test_schema_upgrade_backfills_new_kinds_once_without_recounting_turns(self):
        def entry(cursor,kind,at):
            return json.dumps({'__CURSOR':cursor,'_SYSTEMD_USER_UNIT':'minecraft-agent@a.service',
                               'MESSAGE':json.dumps({'time':at,'kind':kind})})
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);events=run/'decisions-and-turns.jsonl'
            events.write_text(json.dumps({'journal_cursor':'one','player':'a','time':1,'kind':'turn_started'})+'\n')
            state={'journal_cursor':'three','a':{'offset':1024,'totals':{'input_tokens':50}}}
            stdout='\n'.join([entry('one','turn_started',1),entry('two','watch_filtered',2),
                               entry('three','permission_context_supplied',3)])
            with patch('measure_attention.subprocess.run',return_value=SimpleNamespace(stdout=stdout)) as command:
                collect_journal(run,['a'],0,state)
                self.assertIn('--since',command.call_args.args[0])
                self.assertNotIn('--after-cursor',command.call_args.args[0])
            rows=[json.loads(s) for s in events.read_text().splitlines()]
            self.assertEqual([s['kind'] for s in rows],['turn_started','watch_filtered','permission_context_supplied'])
            self.assertEqual(state['a'],{'offset':1024,'totals':{'input_tokens':50}})
            # A re-read of the same journal (including recovery after an interrupted
            # cursor write) must not inflate either turns or the added telemetry.
            with patch('measure_attention.subprocess.run',return_value=SimpleNamespace(stdout=stdout)) as command:
                collect_journal(run,['a'],0,state)
                self.assertIn('--after-cursor',command.call_args.args[0])
            self.assertEqual(len(events.read_text().splitlines()),3)


if __name__ == "__main__":
    unittest.main()
