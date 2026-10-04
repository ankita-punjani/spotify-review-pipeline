"""Standardized grading/ export (GRADING_CONTRACT.md). Code only; reads saved run artifacts."""

import gzip
import json
import shutil
from pathlib import Path

from .enrich import LABEL_CONFIG
from .io import ROOT, file_sha, read_json, read_jsonl, write_json

CALL_KEYS = ("request_id", "role", "review_ids", "model", "phase", "outcome", "label_config", "input_tokens", "output_tokens")


def export_grading(input_csv, run_dir, out_dir=None, extra_call_logs=()):
    run_dir = Path(run_dir)
    out = Path(out_dir or run_dir / "grading")
    out.mkdir(parents=True, exist_ok=True)
    rows = read_json(run_dir / "data_manifest.json")["records"]
    configs = {r["label_config"] for r in read_jsonl(run_dir / "records.jsonl") if r["status"] == "completed"}
    write_json(out / "run.json", {"version": "a5-audit-v1", "analysis_count": rows, "analysis_sha256": file_sha(input_csv),
                                  "classification_input_fields": ["review_text"], "allow_multi_issue": False,
                                  "run_id": run_dir.name, "enrich_label_config": sorted(configs) if len(configs) > 1 else next(iter(configs), LABEL_CONFIG)})
    shutil.copyfile(run_dir / "ingestion.json", out / "ingestion.json")
    with (run_dir / "records.jsonl").open("rb") as src, gzip.open(out / "records.jsonl.gz", "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copyfile(run_dir / name, out / name)

    # Call log: enrichment calls under the configuration(s) of the exported records, plus every verify/group/memo call.
    calls = []
    for path in (run_dir / "calls.jsonl", *map(Path, extra_call_logs)):
        for c in read_jsonl(path):
            if c["role"] == "enrich" and c["label_config"] not in configs:
                continue
            calls.append({k: c[k] for k in CALL_KEYS} | {k: c[k] for k in ("cached_input_tokens", "reasoning_tokens", "cost_usd",
                                                                            "started_at", "latency_s", "error", "prompt_version",
                                                                            "reasoning_effort", "run_id") if k in c})
    with gzip.open(out / "calls.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False, separators=(",", ":")) + "\n")
    for name in ("checkpoint_before.json", "checkpoint_after.json"):
        if (run_dir / name).exists():
            snap = read_json(run_dir / name)
            write_json(out / name, {"completed_ids": snap["completed_ids"]})
    return {"out": str(out), "calls": len(calls)}
