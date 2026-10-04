"""run_summary.json: statuses, retries, failures, tokens, cost by role, elapsed time, spend limit, resume evidence."""

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .io import now, read_json, read_jsonl, write_json


def summarize(run_dir, extra_call_logs=()):
    run = Path(run_dir)
    calls = read_jsonl(run / "calls.jsonl")
    for p in extra_call_logs:
        calls += read_jsonl(p)
    recs = read_jsonl(run / "records.jsonl")
    by_role = defaultdict(lambda: Counter())
    for c in calls:
        r = by_role[c["role"]]
        r["calls"] += 1
        r["failed_calls"] += c["outcome"] == "failed"
        r["salvaged_calls"] += str(c.get("error") or "").startswith("salvaged")
        r["retry_calls"] += c.get("enrich_attempt") == 2
        r["input_tokens"] += c["input_tokens"]
        r["cached_input_tokens"] += c.get("cached_input_tokens") or 0
        r["output_tokens"] += c["output_tokens"]
        r["reasoning_tokens"] += c.get("reasoning_tokens") or 0
        r["cost_usd_micro"] += round((c.get("cost_usd") or 0) * 1e6)
    roles = {k: {**{x: v[x] for x in v if x != "cost_usd_micro"}, "cost_usd": round(v["cost_usd_micro"] / 1e6, 4)} for k, v in by_role.items()}
    db = sqlite3.connect(run / "state.sqlite")
    sessions = [dict(zip([d[0] for d in db.execute("SELECT * FROM sessions").description], r))
                for r in db.execute("SELECT * FROM sessions ORDER BY session")]
    enrich_sessions = [read_json(p) for p in sorted(run.glob("enrich_session_*.json"))]
    status = Counter(r["status"] for r in recs)
    reasons = Counter(r.get("reason") for r in recs if r["status"] != "completed")
    out = {"run_id": run.name, "generated_at": now(),
           "input": read_json(run / "data_manifest.json"),
           "records": {"total": len(recs), "completed": status["completed"], "quarantined": status["quarantined"],
                       "quarantine_reasons": dict(reasons),
                       "completed_via_exact_text_cache": sum(bool(r.get("cache_source_id")) for r in recs),
                       "completed_needs_review": sum(bool(r.get("needs_review")) for r in recs if r["status"] == "completed")},
           "label_configs": sorted({r["label_config"] for r in recs if r["status"] == "completed"}),
           "calls_by_role": roles,
           "total_cost_usd_measured": round(sum(v["cost_usd"] for v in roles.values()), 4),
           "cost_basis": "measured provider usage x cost/rates.csv (standard tier); compare with the OpenAI usage dashboard",
           "spend_limit_usd": json.loads((run / "spend.json").read_text())["cap_usd"],
           "enrich_sessions": [{k: s[k] for k in ("session", "phase", "originals_completed_this_session", "first_attempt_invalid_items",
                                                  "elapsed_s", "stop_reason")} for s in enrich_sessions],
           "sessions_table": sessions,
           "enrich_elapsed_s_total": round(sum(s["elapsed_s"] for s in enrich_sessions), 1),
           "resume_evidence": {"checkpoint_before": len(read_json(run / "checkpoint_before.json")["completed_ids"]),
                               "checkpoint_after": len(read_json(run / "checkpoint_after.json")["completed_ids"])}}
    write_json(run / "run_summary.json", out)
    return out
