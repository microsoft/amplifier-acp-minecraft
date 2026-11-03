"""Read-only attention accounting. Planner turns are not provider requests.

Optional engine readers supply usage evidence; they are measurement adapters,
not requirements imposed on an ACP agent or on the Minecraft connection.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import statistics
import subprocess
import time

if __package__:
    from .observe_run import task_evidence
else:
    from observe_run import task_evidence

KINDS = {"initialized", "session_loaded", "turn_started", "turn_completed",
         "turn_error", "watch_evaluated", "watch_applied", "watch_error",
         "watch_bridge_error", "agent_assessment", "assessment_applied",
         "assessment_discarded", "assessment_error", "adapter_error",
         "connection_retry_wait", "session_load_progress", "budget_wait",
         "budget_resumed", "usage", "continuation_policy", "watch_filtered",
         "permission_context_supplied"}
JOURNAL_KINDS_VERSION = 2


def stamp(value):
    return float(value) if isinstance(value, (float, int)) else datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def read_lines(path):
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                # A simultaneously appended final line can be incomplete.
                continue
    return rows


def usage(value):
    details = value.get("input_tokens_details") or {}
    return {"input_tokens": value.get("input_tokens", 0),
            "cached_input_tokens": value.get("cached_input_tokens", details.get("cached_tokens", 0)),
            "cache_write_input_tokens": value.get("cache_write_input_tokens", details.get("cache_write_tokens", 0)),
            "output_tokens": value.get("output_tokens", 0),
            "reasoning_output_tokens": value.get("reasoning_output_tokens", (value.get("output_tokens_details") or {}).get("reasoning_tokens", 0))}


def add_usage(total, value):
    for key, number in usage(value).items():
        if isinstance(number, (int, float)) and number >= 0:
            total[key] = total.get(key, 0) + number


def native_reader(spec):
    with sqlite3.connect(Path(spec["path"]).resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT seq,turn,kind,at,data FROM events WHERE session=? AND seq>? AND kind IN ('model.started','model.finished') ORDER BY seq",
                          (spec["session"], spec["baseline_seq"])).fetchall()
    receipts = []
    total = {}
    for seq, turn, kind, at, raw in rows:
        data = json.loads(raw)
        item = {"id": seq, "turn": turn, "kind": kind, "at": at, "index": data.get("index")}
        if kind == "model.finished":
            item["usage"] = usage(data.get("usage") or {})
            add_usage(total, item["usage"])
        receipts.append(item)
    return {"source": "native runtime model.started/model.finished events",
            "requests_started": sum(r["kind"] == "model.started" for r in receipts),
            "responses_finished": sum(r["kind"] == "model.finished" for r in receipts),
            "usage": total, "receipts": receipts}


def codex_reader(spec, cursor):
    """Count distinct usage updates, without assuming one update per request."""
    cursor.setdefault("offset", spec["baseline_offset"])
    cursor.setdefault("totals", spec.get("baseline_totals"))
    cursor.setdefault("receipts", [])
    cursor.setdefault("usage", {})
    cursor.setdefault("counter_resets", 0)
    path = Path(spec["path"])
    if path.stat().st_size < cursor["offset"]:
        raise ValueError("Usage log shrank; preserve baseline and inspect rotation")
    with path.open("rb") as handle:
        handle.seek(cursor["offset"])
        while line := handle.readline():
            if not line.endswith(b"\n"):
                break
            row = json.loads(line)
            cursor["offset"] = handle.tell()
            payload = row.get("payload") or {}
            if row.get("type") != "event_msg" or payload.get("type") != "token_count":
                continue
            totals = (payload.get("info") or {}).get("total_token_usage")
            if not totals or totals == cursor["totals"]:
                continue
            old = cursor["totals"]
            cursor["totals"] = totals
            if old is None:
                continue  # No defensible delta from an unknown baseline.
            delta = {k: usage(totals)[k] - usage(old)[k] for k in usage(totals)}
            if any(v < 0 for v in delta.values()):
                cursor["counter_resets"] += 1
                continue  # A reset must not become fabricated consumption.
            add_usage(cursor["usage"], delta)
            cursor["receipts"].append({"at": row["timestamp"], "kind": "usage_update", "usage": delta})
    return {"source": "Codex distinct cumulative token-usage updates",
            "requests_started": None,
            "usage_updates_observed": len(cursor["receipts"]),
            "counter_resets": cursor["counter_resets"],
            "usage": cursor["usage"], "receipts": cursor["receipts"],
            "limitation": "No request-start event here; failed/unreported requests may be absent."}


def journal_summary(events, now):
    counts = Counter()
    admissions = []
    wake = None
    capacity_start = None
    capacity_spans = []
    latencies = []
    for event in sorted(events, key=lambda e: stamp(e["time"])):
        kind = event["kind"]
        counts[kind] += 1
        if kind in ("watch_evaluated", "agent_assessment") and event.get("result"):
            latencies.append(event["elapsed_ms"])
            for key, amount in usage(event["result"].get("usage") or {}).items():
                counts["decision_" + key] += amount
        if kind == "agent_assessment":
            counts["waiting_assessments" if event.get("phase") == "waiting" else "active_turn_advisories"] += 1
        if kind == "watch_evaluated":
            if event.get("evaluator") == "predicate":
                counts["exact_predicate_evaluations"] += 1
            elif event.get("result"):
                counts["semantic_evaluations"] += 1
                receipts = event.get("receipts", [])
                if receipts:
                    counts["semantic_wake_results" if any(r.get("wake") for r in receipts) else "semantic_hold_results"] += 1
        if kind == "watch_filtered":
            # Filtering 19 pieces of evidence is not 19 avoided model calls.
            # An eligible branch in the same batch may still call a decision model.
            amount = event.get("events", 0)
            if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0:
                counts["metadata_filtered_events"] += amount
            called = event.get("model_called")
            suffix = ("with_model_call" if called is True else "without_model_call"
                      if called is False else "model_call_unknown")
            counts["metadata_filter_batches_" + suffix] += 1
        if kind in ("watch_applied", "assessment_applied") and event.get("application") == "wake":
            wake = "semantic_or_exact_watch" if kind == "watch_applied" else "waiting_assessment"
        if kind == "turn_started":
            sources = {m.get("source") for m in event.get("messages", [])}
            reason = ("human_request" if "human" in sources else "peer_request" if "agent" in sources
                      else wake or "active_work_continuation")
            admissions.append({"at": event["time"], "reason": reason})
            wake = None
        if kind == "budget_wait" and capacity_start is None:
            capacity_start = stamp(event["time"])
        if kind == "budget_resumed" and capacity_start is not None:
            capacity_spans.append([capacity_start, stamp(event["time"])])
            capacity_start = None
    if capacity_start is not None:
        capacity_spans.append([capacity_start, now])
    return {"counts": dict(counts), "planner_admissions": admissions,
            "admission_reasons": dict(Counter(x["reason"] for x in admissions)),
            "median_decision_roundtrip_ms": statistics.median(latencies) if latencies else None,
            "capacity_wait_seconds": sum(end-start for start, end in capacity_spans),
            "capacity_wait_spans": capacity_spans}


def idle_intervals(samples, name, journal, model, expected_task_id=None):
    """Conservative sample intervals, not inferred continuous availability."""
    total = Counter()
    starts = [stamp(x["at"]) for x in journal["planner_admissions"]]
    unexplained = []
    previous = None
    for row in sorted(samples, key=lambda s: stamp(s["at"])):
        current = row.get("players", {}).get(name, {})
        if previous is not None:
            prev_at, prev = previous
            now = stamp(row["at"])
            elapsed = now-prev_at
            status = (current.get("task") or {}).get("status")
            stable = ((current.get("task") or {}).get("id") == (prev.get("task") or {}).get("id")
                      and (expected_task_id is None or (current.get("task") or {}).get("id") == expected_task_id)
                      and status == (prev.get("task") or {}).get("status")
                      and status in ("waiting", "review", "blocked", "budget_exhausted")
                      and current.get("ready") and prev.get("ready")
                      and not current.get("turn_active") and not prev.get("turn_active")
                      and not current.get("busy") and not prev.get("busy"))
            capacity = any(a < now and b > prev_at for a, b in journal["capacity_wait_spans"])
            admitted = any(prev_at < x <= now for x in starts)
            if stable and 0 < elapsed <= 60 and not capacity and not admitted:
                total[status] += elapsed
                unexplained.extend(r for r in model.get("receipts", [])
                                   if r["kind"] == "model.started" and prev_at < stamp(r["at"]) <= now)
        previous = (stamp(row["at"]), current)
    return {"sampled_idle_seconds_by_state": dict(total),
            "native_requests_inside_idle_intervals": unexplained,
            "limitation": "Both samples must be idle with no recorded admission/capacity wait between them; intervals over 60 seconds are excluded."}


def collect_journal(run, players, since, state):
    command = ["journalctl", "--user", "--no-pager", "--all", "-o", "json"]
    for name in players:
        command += ["-u", f"minecraft-agent@{name}.service"]
    # A schema upgrade re-reads retained journals from the original run start.
    # Keep provider baselines intact and deduplicate by system journal cursor;
    # advancing a previous version's cursor already skipped these new kinds.
    current_schema = state.get("journal_kinds_version") == JOURNAL_KINDS_VERSION
    command += (["--after-cursor", state["journal_cursor"]]
                if current_schema and state.get("journal_cursor") else ["--since", "@"+str(since)])
    result = subprocess.run(command, check=True, text=True, capture_output=True, timeout=30)
    seen = {row.get("journal_cursor") for row in read_lines(run/"decisions-and-turns.jsonl")}
    with (run/"decisions-and-turns.jsonl").open("a") as output:
        for line in result.stdout.splitlines():
            entry = json.loads(line)
            state["journal_cursor"] = entry.get("__CURSOR", state.get("journal_cursor"))
            try:
                row = json.loads(entry.get("MESSAGE", ""))
            except ValueError:
                continue
            if row.get("kind") in KINDS and entry["__CURSOR"] not in seen:
                row["player"] = entry["_SYSTEMD_USER_UNIT"].removeprefix("minecraft-agent@").removesuffix(".service")
                row["journal_cursor"] = entry["__CURSOR"]
                output.write(json.dumps(row)+"\n")
                seen.add(entry["__CURSOR"])
    state["journal_kinds_version"] = JOURNAL_KINDS_VERSION


def measure(run, root):
    manifest = json.loads((run/"briefs.json").read_text())
    inputs = json.loads((run/"measurement-inputs.json").read_text()) if (run/"measurement-inputs.json").exists() else {}
    path = run/"efficiency-cursor.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    now = time.time()
    collect_journal(run, manifest["players"], stamp(manifest["started_at"]), state)
    journal = list({r["journal_cursor"]:r for r in read_lines(run/"decisions-and-turns.jsonl")}.values())
    samples = read_lines(run/"observations/samples.jsonl")
    result = {"at": datetime.now(timezone.utc).isoformat(), "players": {}, "llm_savings_estimated": False,
              "limitations": ["A held decision is not automatically an avoided LLM request: there is no randomized LLM-first control.",
                              "Active-turn decision advice is separated from pre-wake decisions.",
                              "Filtered evidence counts are not avoided model requests; eligible branches may still call a decision model.",
                              "The last work report is historical agent-reported evidence, not current authority or independent acceptance.",
                              "Provider usage is optional engine-specific evidence; ACP remains the connection boundary.",
                              "Token totals are not dollar costs; cached input is reported separately."]}
    for name in manifest["players"]:
        rows = [e for e in journal if e["player"] == name]
        summary = journal_summary(rows, now)
        try:
            spec = inputs.get(name, {})
            model = native_reader(spec) if spec.get("kind") == "native_sqlite" else codex_reader(spec, state.setdefault(name, {})) if spec.get("kind") == "codex_usage" else {"source":"unavailable", "requests_started":None}
        except Exception as error:
            model = {"source":"unavailable", "requests_started":None,"error_type":type(error).__name__}
        expected_task = (manifest.get("accepted_tasks", {}).get(name) or {}).get("id")
        idle = idle_intervals(samples, name, summary, model, expected_task)
        data = json.loads((root/name/"workshop.json").read_text())
        task = data.get("task") or {}
        watch = json.loads((root/name/"watches.json").read_text()) if (root/name/"watches.json").exists() else {}
        result["players"][name] = {"task_id":task.get("id"),"status":task.get("status"),"turns":task.get("turns"),
                                    "task_work_turns":task.get("turns"),
                                    "acp_turns_started":summary["counts"].get("turn_started",0),
                                    **task_evidence(task,data,now*1000),
                                    "scheduling":summary,"idle":idle,
                                    "models":{k:v for k,v in model.items() if k != "receipts"},
                                    "watch_calls_in_rolling_hour":sum(t > (now-3600)*1000 for t in watch.get("calls",[]))}
        write(run/(name+"-model-receipts.json"), model)
    write(path, state)
    write(run/"efficiency.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=7200)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    manifest = json.loads((args.run/"briefs.json").read_text())
    # Restarting this observer cannot extend the experiment's observation window.
    end = min(time.time()+max(0,args.seconds), stamp(manifest["started_at"])+manifest.get("limits",{}).get("max_seconds",7200)+900)
    while True:
        report = measure(args.run, args.root)
        print(json.dumps({"at":report["at"],"status":{n:s["status"] for n,s in report["players"].items()}}), flush=True)
        if args.once or time.time() >= end:
            break
        time.sleep(20)
