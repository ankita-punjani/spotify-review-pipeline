"""Turn the run's SQLite state into saved, inspectable record files (code only)."""

import json
from pathlib import Path

from .enrich import State
from .io import read_source, row_sha, write_jsonl

GRADING_KEYS = ("review_id", "source_sha256", "status", "topic", "intent", "sentiment", "severity", "entities",
                "evidence_quote", "needs_review", "label_config")


def export_records(input_csv, run_dir):
    """Write enriched.jsonl (completed, with notes), quarantine.jsonl, and records.jsonl
    (exactly one final record per source ID, in source order). Unfinished rows are exported as
    quarantined with reason 'unresolved_pending' so every ID stays accounted for."""
    run_dir = Path(run_dir)
    state = State(run_dir / "state.sqlite").all()
    enriched, quarantine, records = [], [], []
    for row in read_source(input_csv):
        rid = row["review_id"]
        rec = state.get(rid)
        sha = row_sha(row)
        if rec and rec["status"] == "completed":
            f = json.loads(rec["fields"])
            full = {"review_id": rid, "source_sha256": sha, "status": "completed", **f,
                    "label_config": rec["label_config"]}
            if rec["cache_source_id"]:
                full["cache_source_id"] = rec["cache_source_id"]
            records.append({k: full[k] for k in (*GRADING_KEYS, "subtopic", "cache_source_id") if k in full})
            enriched.append({**full, "attempts": rec["attempts"], "phase": rec["phase"],
                             "notes": json.loads(rec["notes"]) if rec["notes"] else []})
        else:
            reason = rec["reason"] if rec and rec["status"] == "quarantined" else "unresolved_pending"
            q = {"review_id": rid, "source_sha256": sha, "status": "quarantined", "reason": reason,
                 "attempts": rec["attempts"] if rec else 0}
            quarantine.append(q)
            records.append({k: q[k] for k in ("review_id", "source_sha256", "status", "reason")})
    write_jsonl(run_dir / "enriched.jsonl", enriched)
    write_jsonl(run_dir / "quarantine.jsonl", quarantine)
    write_jsonl(run_dir / "records.jsonl", records)
    return {"records": len(records), "completed": len(enriched), "quarantined": len(quarantine),
            "cache_reuse": sum(1 for r in enriched if r.get("cache_source_id"))}
