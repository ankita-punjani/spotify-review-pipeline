"""Golden-50 evaluation: human labels (evals/golden_labels.json) vs the full run's saved predictions.

No model calls. Human labels were exported from tools/label_golden.html (star ratings hidden) before any
model output on these 50 reviews was viewed, and were never used in prompts, examples or thresholds.

    .venv/bin/python evals/golden_eval.py runs/full
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.io import TOPICS, read_jsonl, read_source, write_json  # noqa: E402

SENTIMENT_TOLERANCE = 0.3  # predeclared, same as the verifier comparison
INTENT_NAMES = ("cancellation", "complaint", "request", "praise", "unclear")


def alternatives(g):
    """Accepted alternative labels. The labeler typed them in the note ("also accept billing / sev 4") rather than
    using the form's shift-click fields, so both sources are merged. Only the labeler's own words are used."""
    import re
    alt = {"topic": set(g.get("alt_topic", [])), "intent": set(g.get("alt_intent", [])), "severity": set(g.get("alt_severity", []))}
    m = re.search(r"also accept (.+?)(?:\.\s*Note:|$)", g.get("notes", ""), flags=re.I)
    if m:
        for tok in (t.strip().lower() for t in m.group(1).split("/")):
            sev = re.fullmatch(r"(?:sev(?:erity)?\s*)?([1-5])", tok)
            if tok in TOPICS:
                alt["topic"].add(tok)
            elif tok in INTENT_NAMES:
                alt["intent"].add(tok)
            elif sev:
                alt["severity"].add(int(sev.group(1)))
    return alt


def main(run):
    run = Path(run)
    gold = json.loads((ROOT / "evals" / "golden_labels.json").read_text())["rows"]
    text = {r["review_id"]: r["review_text"] for r in read_source(ROOT / "data" / "golden_50_to_label.csv")}
    preds = {r["review_id"]: r for r in read_jsonl(run / "records.jsonl") if r["review_id"] in text}
    enriched = {r["review_id"]: r for r in read_jsonl(run / "enriched.jsonl") if r["review_id"] in text}

    agree, n_pred = Counter(), 0
    sev_err, sev_err_lenient, sent_err = 0, 0, 0.0
    confusion = defaultdict(Counter)
    per_topic = defaultdict(lambda: {"human": 0, "model": 0, "agree": 0})
    cases, disagreements = [], []
    ent_h = ent_m = ent_both = 0
    quote_ok = 0
    nr = Counter()
    for g in gold:
        rid = g["review_id"]
        p = preds.get(rid)
        ok_pred = bool(p and p["status"] == "completed")
        alt = alternatives(g)
        acc_topic = {g["topic"], *alt["topic"]}
        acc_intent = {g["intent"], *alt["intent"]}
        acc_sev = {g["severity"], *alt["severity"]}
        res = {"review_id": rid, "text": text[rid], "human": {k: g[k] for k in ("topic", "intent", "severity", "sentiment", "entities", "evidence_quote", "needs_review")},
               "ambiguous": g["ambiguous"], "accepted": {"topic": sorted(acc_topic), "intent": sorted(acc_intent), "severity": sorted(acc_sev)},
               "human_note": g.get("notes", "")}
        per_topic[g["topic"]]["human"] += 1
        if not ok_pred:
            res["model"] = None
            res.update({f: False for f in ("topic_strict", "topic_lenient", "intent_strict", "intent_lenient", "severity_strict", "severity_lenient")})
            cases.append(res)
            disagreements.append(res)
            continue
        n_pred += 1
        m = {k: p[k] for k in ("topic", "subtopic", "intent", "severity", "sentiment", "entities", "evidence_quote", "needs_review")}
        res["model"] = m
        res["model_notes"] = enriched.get(rid, {}).get("notes", [])
        res["cache_source_id"] = p.get("cache_source_id")
        res["topic_strict"] = m["topic"] == g["topic"]
        res["topic_lenient"] = m["topic"] in acc_topic
        res["intent_strict"] = m["intent"] == g["intent"]
        res["intent_lenient"] = m["intent"] in acc_intent
        res["severity_strict"] = m["severity"] == g["severity"]
        res["severity_lenient"] = m["severity"] in acc_sev
        res["sentiment_within_tol"] = abs(m["sentiment"] - g["sentiment"]) <= SENTIMENT_TOLERANCE
        res["quote_exact_substring"] = m["evidence_quote"] in text[rid]
        for f in ("topic_strict", "topic_lenient", "intent_strict", "intent_lenient", "severity_strict", "severity_lenient", "sentiment_within_tol", "quote_exact_substring"):
            agree[f] += res[f]
        agree["all_three_strict"] += res["topic_strict"] and res["intent_strict"] and res["severity_strict"]
        agree["all_three_lenient"] += res["topic_lenient"] and res["intent_lenient"] and res["severity_lenient"]
        sev_err += abs(m["severity"] - g["severity"])
        sev_err_lenient += min(abs(m["severity"] - s) for s in acc_sev)
        sent_err += abs(m["sentiment"] - g["sentiment"])
        confusion[g["topic"]][m["topic"]] += 1
        per_topic[m["topic"]]["model"] += 1
        per_topic[g["topic"]]["agree"] += res["topic_strict"]
        he = {e.lower() for e in g["entities"]}
        me = {e.lower() for e in m["entities"]}
        ent_h += len(he)
        ent_m += len(me)
        ent_both += len(he & me)
        res["entities_model_not_in_text"] = [e for e in m["entities"] if e.lower() not in text[rid].lower()]
        wrong = not (res["topic_lenient"] and res["intent_lenient"] and res["severity_lenient"])
        nr[(m["needs_review"], wrong)] += 1
        if not (res["topic_strict"] and res["intent_strict"] and res["severity_strict"]):
            disagreements.append(res)
        cases.append(res)

    n = len(gold)
    summary = {
        "cases": n, "valid_predictions": n_pred, "missing_or_quarantined_predictions": n - n_pred,
        "ambiguous_cases_marked_by_human": sum(g["ambiguous"] for g in gold),
        "cases_with_accepted_alternatives": sum(any(alternatives(g).values()) for g in gold),
        "alternatives_source": "labeler's note text after 'also accept' (shift-click alternative fields were unused)",
        "agreement_denominator_note": "All 50 cases are in every denominator; missing predictions count as wrong.",
        "agreement": {f: round(agree[f] / n, 4) for f in ("topic_strict", "topic_lenient", "intent_strict", "intent_lenient",
                                                           "severity_strict", "severity_lenient", "all_three_strict", "all_three_lenient")},
        "severity_mae_vs_primary": round(sev_err / n_pred, 4) if n_pred else None,
        "severity_mae_vs_closest_accepted": round(sev_err_lenient / n_pred, 4) if n_pred else None,
        "sentiment_mae": round(sent_err / n_pred, 4) if n_pred else None,
        "sentiment_within_tolerance": round(agree["sentiment_within_tol"] / n, 4), "sentiment_tolerance": SENTIMENT_TOLERANCE,
        "evidence_quote_exact_substring": f"{agree['quote_exact_substring']}/{n_pred}",
        "entities": {"human_total": ent_h, "model_total": ent_m, "overlap": ent_both,
                     "model_entities_not_literally_in_text": sum(len(c.get("entities_model_not_in_text", [])) for c in cases)},
        "needs_review_as_predictor": {"flagged_and_wrong": nr[(True, True)], "flagged_and_right": nr[(True, False)],
                                      "unflagged_and_wrong": nr[(False, True)], "unflagged_and_right": nr[(False, False)],
                                      "wrong_means": "outside the human's accepted topic/intent/severity"},
        "per_topic_counts": {t: per_topic[t] for t in TOPICS if any(per_topic[t].values())},
        "topic_confusion_rows_human_cols_model": {h: dict(c) for h, c in sorted(confusion.items())},
    }
    write_json(ROOT / "evals" / "golden_eval.json", {"summary": summary, "cases": cases})
    write_json(ROOT / "evals" / "golden_disagreements.json", disagreements)

    # Checker-format benchmark (accepted label lists), so check_submission.py --gold can score it too.
    bench = {"version": "golden-human-v1", "cases": [{"review_id": g["review_id"], "status": "approved", "reviewer": "student",
                                                       "accepted_topic": sorted({g["topic"], *alternatives(g)["topic"]}),
                                                       "accepted_intent": sorted({g["intent"], *alternatives(g)["intent"]}),
                                                       "accepted_severity": sorted({g["severity"], *alternatives(g)["severity"]})} for g in gold]}
    write_json(ROOT / "evals" / "golden_benchmark.json", bench)

    md = ["# Golden-50 evaluation (human labels vs full-run predictions)\n",
          f"Run: `{run}` · cases {n} · valid predictions {n_pred} · human-marked ambiguous {summary['ambiguous_cases_marked_by_human']}\n",
          "| measure | strict (human primary label) | lenient (any label the human accepted) |", "|---|---:|---:|"]
    a = summary["agreement"]
    for f in ("topic", "intent", "severity", "all_three"):
        md.append(f"| {f.replace('_', ' ')} agreement | {a[f + '_strict']:.0%} | {a[f + '_lenient']:.0%} |")
    md += ["", f"- Severity MAE: {summary['severity_mae_vs_primary']} vs primary, {summary['severity_mae_vs_closest_accepted']} vs closest accepted.",
           f"- Sentiment MAE {summary['sentiment_mae']}; within ±{SENTIMENT_TOLERANCE}: {summary['sentiment_within_tolerance']:.0%}.",
           f"- Evidence quotes that are exact source substrings: {summary['evidence_quote_exact_substring']}.",
           f"- Entities: human {ent_h}, model {ent_m}, overlap {ent_both}; model entities not literally in the text: "
           f"{summary['entities']['model_entities_not_literally_in_text']}.",
           f"- needs_review as a predictor: {json.dumps(summary['needs_review_as_predictor'])}", "",
           "## Topic confusion (rows = human, columns = model)\n", "| human \\ model | " + " | ".join(TOPICS) + " |",
           "|---|" + "---:|" * len(TOPICS)]
    for h in TOPICS:
        if h in confusion:
            md.append(f"| {h} | " + " | ".join(str(confusion[h].get(t, "")) for t in TOPICS) + " |")
    md += ["", "## Every disagreement (strict)\n", "| # | review | human | model | accepted alternatives? | human note |", "|---|---|---|---|---|---|"]
    for i, d in enumerate(disagreements, 1):
        h, m = d["human"], d["model"]
        mm = f"{m['topic']}/{m['intent']}/{m['severity']}" if m else "missing"
        within = "yes" if m and d["topic_lenient"] and d["intent_lenient"] and d["severity_lenient"] else "no"
        md.append(f"| {i} | {d['text'][:110].replace('|', '/').replace(chr(10), ' ')} | {h['topic']}/{h['intent']}/{h['severity']} | {mm} | {within} | {d['human_note'][:80]} |")
    (ROOT / "evals" / "golden_eval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("valid_predictions", "agreement", "severity_mae_vs_primary", "sentiment_mae")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/full")
