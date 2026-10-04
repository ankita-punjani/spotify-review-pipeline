"""Stage 6 — Recommend. The memo role sees only saved aggregates and a bounded evidence pack.
Code builds the claims table, then checks every claim ID, number, issue ID and review ID in the draft.
One redraft is allowed with the violations listed; a draft that still fails is saved and flagged for a person.
"""

import csv
import json
import re
from pathlib import Path

from .io import ROOT, now, read_json, read_jsonl, read_source, write_json
from .llm import LLM, Ledger

PROMPT_VERSION = "memo_v2"
MODEL, EFFORT = "gpt-6-luna", "medium"
LABEL_CONFIG = f"{MODEL}+{PROMPT_VERSION}+effort-{EFFORT}"
METRICS = ("complaint_count", "severity_sum", "mean_severity", "priority_score")
CANDIDATE_TOPICS = ("access", "usability", "playback", "billing", "support")
TOP_ISSUES = 10
EVIDENCE_PER_ISSUE = 4
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _csv(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_pack(input_csv, run_dir):
    """Bounded memo input: aggregates plus a few representative reviews per selected issue."""
    run_dir = Path(run_dir)
    ranking = _csv(run_dir / "ranking.csv")
    topics = _csv(run_dir / "topic_aggregates.csv")
    aggregates = {r["issue_id"]: r for r in _csv(run_dir / "aggregates.csv")}
    records = read_jsonl(run_dir / "records.jsonl")
    meta = {r["review_id"]: r for r in read_source(input_csv)}

    # Issues covered: the top N overall plus the top issue of every candidate area.
    chosen = [r["issue_id"] for r in ranking[:TOP_ISSUES]]
    for t in CANDIDATE_TOPICS:
        best = next((r["issue_id"] for r in ranking if r["issue_id"].startswith(t + ".")), None)
        if best and best not in chosen:
            chosen.append(best)

    claims, n = [], 0
    for r in ranking:
        if r["issue_id"] in chosen:
            for m in METRICS:
                n += 1
                claims.append({"claim_id": f"C{n:03d}", "issue_id": r["issue_id"], "metric": m, "value": r[m]})

    # Representative evidence: original (non-cached) members, highest severity, then most helpful votes, then ID.
    by_issue = {}
    for rec in records:
        if rec["status"] == "completed" and rec["intent"] in ("complaint", "cancellation") and rec["subtopic"] in chosen \
                and not rec.get("cache_source_id"):
            by_issue.setdefault(rec["subtopic"], []).append(rec)
    evidence = []
    for iid in chosen:
        pick = sorted(by_issue.get(iid, []), key=lambda r: (-r["severity"], -int(meta[r["review_id"]]["review_likes"] or 0), r["review_id"]))
        for r in pick[:EVIDENCE_PER_ISSUE]:
            evidence.append({"issue_id": iid, "review_id": r["review_id"], "severity": r["severity"], "intent": r["intent"],
                             "helpful_votes": int(meta[r["review_id"]]["review_likes"] or 0), "quote": r["evidence_quote"][:220]})

    completed = sum(r["status"] == "completed" for r in records)
    coverage = {"source_rows": len(records), "completed": completed, "quarantined": len(records) - completed,
                "empty_text_quarantines": sum(r.get("reason") == "empty_review_text" for r in records),
                "exact_text_cache_reuse": sum(bool(r.get("cache_source_id")) for r in records),
                "ranked_complaints": sum(int(r["complaint_count"]) for r in ranking),
                "missing_app_version_rows": sum(not m["app_version"].strip() for m in meta.values())}
    verification = None
    vpath = run_dir / "verify" / "disagreement_report.json"
    if vpath.exists():
        v = read_json(vpath)
        verification = {"sample": v["n"], "agreement": v["agreement"], "severity_mae": v["severity_mae"]}
    trend = _trend(run_dir)
    names = {}
    if (run_dir / "issues.json").exists():
        names = {i["issue_id"]: i.get("name") for i in read_json(run_dir / "issues.json")["issues"] if i.get("name")}
    pack = {"coverage": coverage, "topic_rollup": topics, "issue_names": {k: v for k, v in names.items() if k in chosen},
            "ranking": [{k: r[k] for k in ("rank", "issue_id", "complaint_count", "mean_severity", "priority_score")}
                        | {"cancellation_count": aggregates[r["issue_id"]]["cancellation_count"],
                           "severity_4plus_count": aggregates[r["issue_id"]]["severity_4plus_count"]} for r in ranking[:15]],
            "claims": claims, "trend": trend, "verification": verification, "evidence": evidence}
    return pack


def _trend(run_dir):
    """Compare complaint share by topic in two comparable full 6-month windows (partial months excluded)."""
    path = Path(run_dir) / "trend_monthly.csv"
    if not path.exists():
        return None
    rows = [r for r in _csv(path) if r["partial_month"] == "False"]
    months = sorted({r["month"] for r in rows})
    if len(months) < 12:
        return {"note": "fewer than 12 full months; no period comparison", "months": months}
    early, late = months[:6], months[-6:]
    out = {"early_window": f"{early[0]}..{early[-1]}", "late_window": f"{late[0]}..{late[-1]}", "by_topic": {}}
    for window, ms in (("early", early), ("late", late)):
        all_reviews = sum(int(r["all_reviews"]) for r in rows if r["month"] in ms and r["topic"] == "other")
        for t in CANDIDATE_TOPICS:
            c = sum(int(r["ranked_complaints"]) for r in rows if r["month"] in ms and r["topic"] == t)
            out["by_topic"].setdefault(t, {})[window] = {"ranked_complaints": c, "all_reviews": all_reviews,
                                                         "share_pct": round(100 * c / all_reviews, 2) if all_reviews else None}
    return out


def _numbers_in(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _numbers_in(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(_norm(str(obj)))
    elif isinstance(obj, str) and re.fullmatch(r"-?\d+(\.\d+)?", obj):
        acc.add(_norm(obj))
    elif isinstance(obj, str):
        for m in re.findall(r"\d{4}-\d{2}", obj):
            acc.update(_norm(x) for x in m.split("-"))
    return acc


def _norm(s):
    s = s.replace(",", "")
    try:
        return format(float(s), "g") if "." in s else str(int(s))
    except ValueError:
        return s


def check(memo, pack):
    """Mechanical checks; returns a list of violations (empty = pass)."""
    problems = []
    claims = {c["claim_id"]: c for c in pack["claims"]}
    for m in re.finditer(r"([-\d.,]+)\s*(?:[A-Za-z%() -]{0,40}?)\[(C\d{3})\]", memo):
        num, cid = m.group(1).strip(".,"), m.group(2)
        if cid not in claims:
            problems.append(f"unknown claim id {cid}")
        elif _norm(num) != _norm(claims[cid]["value"]):
            problems.append(f"{cid}: memo says {num}, saved value is {claims[cid]['value']} ({claims[cid]['metric']} of {claims[cid]['issue_id']})")
    for cid in re.findall(r"\[(C\d{3})\]", memo):
        if cid not in claims:
            problems.append(f"unknown claim id {cid}")
    issue_ids = {r["issue_id"] for r in pack["ranking"]} | {c["issue_id"] for c in pack["claims"]}
    for iid in set(re.findall(r"`([a-z_]+\.[a-z_]+)`", memo)):
        if iid not in issue_ids:
            problems.append(f"issue id not in supplied data: {iid}")
    evidence_ids = {e["review_id"] for e in pack["evidence"]}
    for rid in set(UUID.findall(memo)):
        if rid not in evidence_ids:
            problems.append(f"review id not in evidence pack: {rid}")
    allowed = _numbers_in(pack, set())
    text_wo_ids = UUID.sub("", re.sub(r"\[C\d{3}\]", "", memo))
    text_wo_ids = re.sub(r"`[^`]*`", "", text_wo_ids)
    for num in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", text_wo_ids):
        n = _norm(num.rstrip(".,"))
        if n not in allowed and n not in {str(i) for i in range(0, 11)}:
            problems.append(f"number not found in supplied data: {num}")
    for banned in ("revenue", "churn rate", "retention impact", "revenue at risk"):
        if banned in memo.lower():
            problems.append(f"prohibited claim language: {banned}")
    return sorted(set(problems))


def run_memo(input_csv, run_dir, budget_usd):
    run_dir = Path(run_dir)
    out = run_dir / "memo"
    out.mkdir(exist_ok=True)
    pack = build_pack(input_csv, run_dir)
    write_json(out / "memo_input_pack.json", pack)
    import hashlib
    key = hashlib.sha256((LABEL_CONFIG + json.dumps(pack, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    prev = out / "memo_check.json"
    if prev.exists() and (run_dir / "memo.md").exists():
        old = read_json(prev)
        if old.get("input_hash") == key and old.get("status") == "passed_code_checks":
            return {**old, "cached": True}
    instructions = (ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    schema = {"type": "object", "additionalProperties": False, "properties": {"memo_markdown": {"type": "string"}},
              "required": ["memo_markdown"]}
    llm = LLM(MODEL, EFFORT, Ledger(budget_usd, run_dir / "spend.json"), run_dir / "calls.jsonl", run_dir.name)
    payload = json.dumps(pack, ensure_ascii=False)
    attempts = []
    memo = None
    for attempt in (1, 2):
        extra_note = "" if attempt == 1 else ("\n\nYour previous draft failed these code checks; fix every one and return the full memo:\n- "
                                              + "\n- ".join(attempts[-1]["violations"]) + "\n\nPrevious draft:\n" + memo)
        res = llm.call(role="memo", instructions=instructions, payload=payload + extra_note, schema=schema, schema_name="memo",
                       review_ids=[], phase="initial", label_config=LABEL_CONFIG, max_output_tokens=12000,
                       prompt_version=PROMPT_VERSION, extra={"inputs": ["memo/memo_input_pack.json"], "memo_attempt": attempt})
        if res is None:
            attempts.append({"attempt": attempt, "violations": ["model call failed"]})
            continue
        memo = res["memo_markdown"]
        violations = check(memo, pack)
        attempts.append({"attempt": attempt, "violations": violations})
        (out / f"memo_draft_{attempt}.md").write_text(memo, encoding="utf-8")
        if not violations:
            break
    status = "passed_code_checks" if attempts and not attempts[-1]["violations"] else "needs_human_fix"
    if memo:
        (run_dir / "memo.md").write_text(memo, encoding="utf-8")
    cited = sorted(set(re.findall(r"\[(C\d{3})\]", memo or "")))
    claims = [c for c in pack["claims"] if c["claim_id"] in cited]
    with (run_dir / "claims.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["claim_id", "issue_id", "metric", "value"], lineterminator="\n")
        w.writeheader()
        w.writerows(claims)
    report = {"status": status, "input_hash": key, "attempts": attempts, "claims_cited": len(claims), "generated_at": now(),
              "label_config": LABEL_CONFIG, "human_review": "pending: a person must read memo.md and confirm the argument"}
    write_json(out / "memo_check.json", report)
    return report
