"""Stage 4c — Issue naming and coherence audit (group role).

Membership is already fixed by code (frozen subtopic -> issue_id). For each top-ranked issue the model sees
a bounded seeded sample of member quotes and returns a name, a one-sentence summary, and any examples that
do not fit. It cannot change membership; misfits are reported as a grouping-quality signal.
Results are cached by (issue sample hash + config), so a warm rerun makes no calls.
"""

import csv
import hashlib
import json
from pathlib import Path

from .io import ROOT, now, read_json, read_jsonl, write_json
from .llm import LLM, Ledger
from .rank import issue_names

PROMPT_VERSION = "name_v1"
MODEL, EFFORT = "gpt-6-luna", "low"
LABEL_CONFIG = f"{MODEL}+{PROMPT_VERSION}+effort-{EFFORT}"
TOP_N = 15
EXAMPLES = 12
SEED = "name-v1"


def run_group(run_dir, budget_usd):
    run_dir = Path(run_dir)
    with (run_dir / "ranking.csv").open(encoding="utf-8", newline="") as f:
        ranking = list(csv.DictReader(f))[:TOP_N]
    records = {r["review_id"]: r for r in read_jsonl(run_dir / "records.jsonl") if r["status"] == "completed"}
    with (run_dir / "membership.csv").open(encoding="utf-8", newline="") as f:
        members = {}
        for row in csv.DictReader(f):
            members.setdefault(row["issue_id"], []).append(row["review_id"])
    defs = issue_names()
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"name": {"type": "string"}, "summary": {"type": "string"},
                             "misfit_ids": {"type": "array", "items": {"type": "string"}}},
              "required": ["name", "summary", "misfit_ids"]}
    instructions = (ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    cache_path = run_dir / "issues.json"
    cache = {i["issue_id"]: i for i in read_json(cache_path)["issues"]} if cache_path.exists() else {}
    llm = None
    issues, calls = [], 0
    for row in ranking:
        iid = row["issue_id"]
        pool = [rid for rid in members.get(iid, []) if not records[rid].get("cache_source_id")]
        sample = sorted(pool, key=lambda rid: hashlib.sha256(f"{SEED}:{rid}".encode()).hexdigest())[:EXAMPLES]
        payload = json.dumps({"issue_id": iid, "definition": defs.get(iid, ""),
                              "examples": [{"id": rid, "quote": records[rid]["evidence_quote"][:240]} for rid in sample]},
                             ensure_ascii=False)
        key = hashlib.sha256((LABEL_CONFIG + payload).encode()).hexdigest()
        if iid in cache and cache[iid].get("input_hash") == key:
            issues.append(cache[iid])
            continue
        llm = llm or LLM(MODEL, EFFORT, Ledger(budget_usd, run_dir / "spend.json"), run_dir / "calls.jsonl", run_dir.name)
        out = llm.call(role="group", instructions=instructions, payload=payload, schema=schema, schema_name="issue_name",
                       review_ids=sample, phase="initial", label_config=LABEL_CONFIG, max_output_tokens=600,
                       prompt_version=PROMPT_VERSION, extra={"stage": "name", "issue_id": iid})
        calls += 1
        entry = {"issue_id": iid, "definition": defs.get(iid, ""), "rank": int(row["rank"]),
                 "member_count": len(members.get(iid, [])), "example_ids": sample, "input_hash": key,
                 "label_config": LABEL_CONFIG}
        if out:
            entry.update({"name": out["name"], "summary": out["summary"],
                          "misfit_ids": [x for x in out["misfit_ids"] if x in sample]})
        else:
            entry.update({"name": None, "summary": None, "misfit_ids": [], "error": "call_failed"})
        issues.append(entry)
    misfits = sum(len(i["misfit_ids"]) for i in issues)
    examined = sum(len(i["example_ids"]) for i in issues)
    write_json(cache_path, {"issues": issues, "generated_at": now(), "label_config": LABEL_CONFIG,
                            "membership_rule": "issue_id = frozen subtopic from taxonomy/subtopics_v1.json (code); "
                                               "names/summaries are model suggestions; membership is never changed by the model",
                            "misfit_rate": round(misfits / examined, 4) if examined else None})
    return {"issues_named": len(issues), "new_calls": calls, "misfits": misfits, "examples_examined": examined}
