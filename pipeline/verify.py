"""Stage 3 — Independent verification.

A separate role (own prompt, own reasoning setting) re-labels a declared seeded random sample from the
review text alone; it never sees the enrichment labels. Code compares the two and writes a disagreement
report. A planted-error test then corrupts labels in a separate test copy and checks that the comparison
catches every corruption (no extra model calls).
"""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .io import INTENTS, ROOT, TOPICS, now, read_jsonl, read_source, write_json, write_jsonl
from .llm import LLM, Ledger

PROMPT_VERSION = "verify_v1"
MODEL, EFFORT = "gpt-6-luna", "low"
LABEL_CONFIG = f"{MODEL}+{PROMPT_VERSION}+effort-{EFFORT}"
BATCH = 10
SEED = "verify-v1"
SENTIMENT_TOLERANCE = 0.3  # predeclared: sentiments within 0.3 count as agreeing


def schema():
    item = {"type": "object", "additionalProperties": False,
            "properties": {"i": {"type": "integer"}, "topic": {"type": "string", "enum": list(TOPICS)},
                           "intent": {"type": "string", "enum": list(INTENTS)},
                           "severity": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                           "sentiment": {"type": "number"}, "confident": {"type": "boolean"}},
            "required": ["i", "topic", "intent", "severity", "sentiment", "confident"]}
    return {"type": "object", "additionalProperties": False,
            "properties": {"results": {"type": "array", "items": item}}, "required": ["results"]}


def sample_ids(records, n):
    """Declared sample: the n completed originals with the lowest sha256(SEED:review_id)."""
    pool = [r["review_id"] for r in records if r["status"] == "completed" and not r.get("cache_source_id")]
    return sorted(pool, key=lambda rid: hashlib.sha256(f"{SEED}:{rid}".encode()).hexdigest())[:n]


def compare(first, second):
    """Field-by-field comparison of two label sets keyed by review_id."""
    ids = sorted(set(first) & set(second))
    agree = Counter()
    sev_err, sent_err = 0, 0.0
    confusion = defaultdict(Counter)
    disagreements = []
    for rid in ids:
        a, b = first[rid], second[rid]
        diff = [f for f in ("topic", "intent") if a[f] != b[f]]
        if a["severity"] != b["severity"]:
            diff.append("severity")
        if abs(a["sentiment"] - b["sentiment"]) > SENTIMENT_TOLERANCE:
            diff.append("sentiment")
        for f in ("topic", "intent", "severity", "sentiment"):
            agree[f] += f not in diff
        agree["all_three"] += not ({"topic", "intent", "severity"} & set(diff))
        sev_err += abs(a["severity"] - b["severity"])
        sent_err += abs(a["sentiment"] - b["sentiment"])
        confusion[a["topic"]][b["topic"]] += 1
        if diff:
            disagreements.append({"review_id": rid, "fields": diff, "first": {k: a[k] for k in ("topic", "intent", "severity", "sentiment")},
                                  "second": {k: b[k] for k in ("topic", "intent", "severity", "sentiment")}})
    n = len(ids)
    return {"n": n, "agreement": {f: round(agree[f] / n, 4) if n else None for f in ("topic", "intent", "severity", "sentiment", "all_three")},
            "severity_mae": round(sev_err / n, 4) if n else None, "sentiment_mae": round(sent_err / n, 4) if n else None,
            "sentiment_tolerance": SENTIMENT_TOLERANCE,
            "topic_confusion_rows_first_cols_second": {k: dict(v) for k, v in sorted(confusion.items())},
            "disagreements": disagreements}


def run_verify(input_csv, run_dir, n, budget_usd, out_dir=None):
    run_dir = Path(run_dir)
    out_dir = Path(out_dir or run_dir / "verify")
    out_dir.mkdir(parents=True, exist_ok=True)
    records = read_jsonl(run_dir / "records.jsonl")
    text = {r["review_id"]: r["review_text"] for r in read_source(input_csv)}
    ids = sample_ids(records, n)
    done_path = out_dir / "verifier_predictions.jsonl"
    done = {r["review_id"]: r for r in read_jsonl(done_path)} if done_path.exists() else {}
    todo = [rid for rid in ids if rid not in done]
    instructions = (ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    llm = LLM(MODEL, EFFORT, Ledger(budget_usd, run_dir / "spend.json"), run_dir / "calls.jsonl", run_dir.name)
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        payload = json.dumps({"reviews": [{"i": k, "t": text[rid]} for k, rid in enumerate(batch, 1)]}, ensure_ascii=False)
        out = llm.call(role="verify", instructions=instructions, payload=payload, schema=schema(), schema_name="verification",
                       review_ids=batch, phase="initial", label_config=LABEL_CONFIG, max_output_tokens=1500,
                       prompt_version=PROMPT_VERSION)
        for item in (out or {}).get("results", []):
            k = item.get("i")
            if type(k) is int and 1 <= k <= len(batch) and batch[k - 1] not in done:
                s = item.get("sentiment")
                if item.get("topic") in TOPICS and item.get("intent") in INTENTS and type(s) in (int, float) and -1 <= s <= 1:
                    done[batch[k - 1]] = {"review_id": batch[k - 1], **{f: item[f] for f in ("topic", "intent", "severity", "sentiment", "confident")}}
        write_jsonl(done_path, [done[r] for r in ids if r in done])
    first = {r["review_id"]: r for r in records if r["review_id"] in done}
    report = compare(first, done)
    for d in report["disagreements"]:
        d["review_text"] = text[d["review_id"]]
        d["verifier_confident"] = done[d["review_id"]]["confident"]
        d["enricher_needs_review"] = first[d["review_id"]]["needs_review"]
    report.update({"sample_declared": n, "sample_method": f"lowest sha256('{SEED}:'+review_id) among completed non-cached records",
                   "verified": len(done), "missing": len(ids) - len(done), "verifier_label_config": LABEL_CONFIG,
                   "generated_at": now()})
    # Does the enricher's own needs_review flag predict disagreement?
    flagged = [rid for rid in first if first[rid]["needs_review"]]
    dis = {d["review_id"] for d in report["disagreements"] if {"topic", "intent", "severity"} & set(d["fields"])}
    report["needs_review_as_predictor"] = {
        "flagged": len(flagged), "flagged_and_disagree": len(dis & set(flagged)),
        "unflagged": len(first) - len(flagged), "unflagged_and_disagree": len(dis - set(flagged))}
    write_json(out_dir / "disagreement_report.json", report)
    planted = planted_error_test(first, done)
    write_json(out_dir / "planted_error_test.json", planted)
    return report, planted


def planted_error_test(first, verifier, k=25):
    """Separate test copy: corrupt topic (and intent) on k records where enricher and verifier agreed,
    then check the comparison flags every corrupted record. Original records are never modified."""
    agreed = sorted(rid for rid in first if first[rid]["topic"] == verifier[rid]["topic"] and first[rid]["intent"] == verifier[rid]["intent"])[:k]
    copy = {rid: dict(first[rid]) for rid in first}
    planted = []
    for n, rid in enumerate(agreed):
        r = copy[rid]
        wrong_topic = TOPICS[(TOPICS.index(r["topic"]) + 3) % len(TOPICS)]
        planted.append({"review_id": rid, "true_topic": r["topic"], "planted_topic": wrong_topic})
        r["topic"] = wrong_topic
        if n % 2 == 0:
            wrong_intent = INTENTS[(INTENTS.index(r["intent"]) + 2) % len(INTENTS)]
            planted[-1].update({"true_intent": r["intent"], "planted_intent": wrong_intent})
            r["intent"] = wrong_intent
    result = compare(copy, verifier)
    flagged = {d["review_id"] for d in result["disagreements"] if "topic" in d["fields"]}
    caught = [p["review_id"] for p in planted if p["review_id"] in flagged]
    return {"synthetic_test": True, "excluded_from_business_aggregates": True, "planted": len(planted),
            "caught": len(caught), "missed": [p for p in planted if p["review_id"] not in flagged],
            "cases": planted, "note": "Labels corrupted only in an in-memory test copy; saved records are untouched."}
