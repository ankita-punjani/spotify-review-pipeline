"""Stages 4b + 5 — Issue membership and the baseline ranking. Code only; no model calls.

Inputs are saved files only: records.jsonl (validated labels) and taxonomy/subtopics_v1.json.
Re-running this on the same inputs produces byte-identical outputs.
"""

import csv
import json
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .io import read_jsonl, read_source, write_json
from .labels import TAXONOMY

RANKED_INTENTS = ("complaint", "cancellation")


def mean6(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _write_csv(path, header, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def issue_names():
    return {s["issue_id"]: s["definition"] for subs in TAXONOMY["topics"].values() for s in subs}


def build(run_dir, input_csv=None):
    run_dir = Path(run_dir)
    records = [r for r in read_jsonl(run_dir / "records.jsonl") if r["status"] == "completed"]

    # Membership: each completed complaint/cancellation belongs to exactly one issue (its frozen subtopic).
    members = sorted((r["subtopic"], r["review_id"]) for r in records if r["intent"] in RANKED_INTENTS)
    _write_csv(run_dir / "membership.csv", ["issue_id", "review_id"], members)

    by_id = {r["review_id"]: r for r in records}
    sev = defaultdict(list)
    for iid, rid in members:
        sev[iid].append(by_id[rid]["severity"])
    ranking = sorted(({"issue_id": iid, "complaint_count": len(v), "severity_sum": sum(v)} for iid, v in sev.items()),
                     key=lambda x: (-x["severity_sum"], x["issue_id"]))
    rows = []
    for rank, x in enumerate(ranking, 1):
        rows.append([rank, x["issue_id"], x["complaint_count"], x["severity_sum"],
                     mean6(x["severity_sum"], x["complaint_count"]), x["severity_sum"]])
    _write_csv(run_dir / "ranking.csv",
               ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"], rows)

    # Additional descriptive aggregates (not part of the baseline score).
    meta = {r["review_id"]: r for r in read_source(input_csv)} if input_csv else {}
    names = issue_names()
    total_complaints = len(members)
    agg = []
    for rank, iid, count, ssum, mean, _ in rows:
        rs = [by_id[rid] for i, rid in members if i == iid]
        c = Counter(r["intent"] for r in rs)
        likes = sum(int(meta[r["review_id"]]["review_likes"] or 0) for r in rs) if meta else ""
        agg.append([rank, iid, iid.split(".")[0], names.get(iid, ""), count, c["cancellation"], ssum, mean,
                    sum(r["severity"] >= 4 for r in rs), sum(r["severity"] == 5 for r in rs),
                    sum(r["needs_review"] for r in rs), mean6(round(sum(r["sentiment"] for r in rs) * 100), count * 100),
                    mean6(count * 100, total_complaints), likes])
    _write_csv(run_dir / "aggregates.csv",
               ["rank", "issue_id", "topic", "definition", "complaint_count", "cancellation_count", "severity_sum",
                "mean_severity", "severity_4plus_count", "severity_5_count", "needs_review_count", "mean_sentiment",
                "share_of_ranked_complaints_pct", "helpful_votes_sum"], agg)

    # Topic roll-up, answering the access / usability / playback / billing-support question directly.
    topic = defaultdict(lambda: [0, 0, 0, 0])
    for iid, rid in members:
        t = topic[iid.split(".")[0]]
        r = by_id[rid]
        t[0] += 1
        t[1] += r["severity"]
        t[2] += r["intent"] == "cancellation"
        t[3] += r["severity"] >= 4
    trows = sorted(([k, v[0], v[1], mean6(v[1], v[0]), v[2], v[3], mean6(v[0] * 100, total_complaints)] for k, v in topic.items()),
                   key=lambda x: (-x[2], x[0]))
    _write_csv(run_dir / "topic_aggregates.csv",
               ["topic", "complaint_count", "severity_sum", "mean_severity", "cancellation_count", "severity_4plus_count",
                "share_of_ranked_complaints_pct"], trows)

    # Monthly trend with denominators (all reviews that month); first and last months are partial.
    if meta:
        month_all = Counter(m["review_timestamp"][:7] for m in meta.values())
        month_topic = Counter((meta[rid]["review_timestamp"][:7], iid.split(".")[0]) for iid, rid in members)
        months = sorted(month_all)
        trend = [[m, month_all[m], t, month_topic[(m, t)], mean6(month_topic[(m, t)] * 100, month_all[m]),
                  m in (months[0], months[-1])] for m in months for t in TAXONOMY["topics"]]
        _write_csv(run_dir / "trend_monthly.csv",
                   ["month", "all_reviews", "topic", "ranked_complaints", "share_of_all_reviews_pct", "partial_month"], trend)

    summary = {"completed_records": len(records), "ranked_complaints": total_complaints, "issues": len(rows),
               "top5": [r[1] for r in rows[:5]]}
    write_json(run_dir / "rank_summary.json", summary)
    return summary
