"""Pipeline CLI. Every stage reads saved inputs and writes saved outputs under runs/<name>/.

  python run.py ingest     --input data/spotify_reviews_18months.csv --run runs/full
  python run.py enrich     --input data/spotify_reviews_18months.csv --run runs/full --budget-usd 35 --workers 4
  python run.py checkpoint --run runs/full --out runs/full/checkpoint_before.json
  python run.py slice      --input data/checkpoint_500.csv --start 100 --count 50 --out data/smoke_50.csv
"""

import argparse
import csv
from pathlib import Path

from pipeline.io import FIELDS, read_source


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="Stage 1: read and profile every row (no model calls)")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)

    s = sub.add_parser("enrich", help="Stage 2: classify nonempty reviews in <=50-review model calls")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--budget-usd", required=True, type=float, help="hard local spend cap for this run directory")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--batch-size", type=int, default=50)
    s.add_argument("--max-batches", type=int, help="dispatch at most N batches this session (for pilots/demos)")
    s.add_argument("--rescue-transient", action="store_true",
                   help="one more attempt for quarantines whose first attempt was a transient API failure")

    s = sub.add_parser("checkpoint", help="Snapshot completed IDs (resume evidence)")
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--out", required=True, type=Path)

    s = sub.add_parser("records", help="Write enriched/quarantine/records.jsonl from saved state (no model calls)")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)

    s = sub.add_parser("verify", help="Stage 3: independent re-label of a declared random sample")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--sample", type=int, default=1000)
    s.add_argument("--budget-usd", required=True, type=float)

    s = sub.add_parser("rank", help="Stages 4b+5: membership + baseline ranking from saved records (no model calls)")
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--input", type=Path, help="optional source CSV for trend/helpful-vote aggregates")

    s = sub.add_parser("group", help="Stage 4c: name top issues + coherence audit (membership unchanged)")
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--budget-usd", required=True, type=float)

    s = sub.add_parser("memo", help="Stage 6: memo from saved aggregates + bounded evidence, with code checks")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--budget-usd", required=True, type=float)

    s = sub.add_parser("grading", help="Write the standardized grading/ folder")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--extra-calls", nargs="*", default=["taxonomy/discovery_v1/calls.jsonl"])

    s = sub.add_parser("all", help="Run every stage in order on one input CSV")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--run", required=True, type=Path)
    s.add_argument("--budget-usd", required=True, type=float, help="shared cap across all model stages")
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--verify-sample", type=int, default=1000)

    s = sub.add_parser("slice", help="Write a contiguous slice of a CSV (development inputs only)")
    s.add_argument("--input", required=True, type=Path)
    s.add_argument("--start", type=int, default=0)
    s.add_argument("--count", type=int, required=True)
    s.add_argument("--out", required=True, type=Path)

    a = p.parse_args()
    if a.cmd == "ingest":
        from pipeline.ingest import ingest
        a.run.mkdir(parents=True, exist_ok=True)
        r = ingest(a.input, a.run)
        print({k: r[k] for k in ("records", "empty_review_text", "distinct_nonempty_texts", "duplicate_review_ids", "file_sha256")})
    elif a.cmd == "enrich":
        from pipeline.enrich import run_enrich
        run_enrich(a.input, a.run, budget_usd=a.budget_usd, workers=a.workers, max_batches=a.max_batches,
                   batch_size=a.batch_size, rescue_transient=a.rescue_transient)
    elif a.cmd == "checkpoint":
        from pipeline.enrich import snapshot
        print("completed_ids:", snapshot(a.run, a.out))
    elif a.cmd == "records":
        from pipeline.records import export_records
        print(export_records(a.input, a.run))
    elif a.cmd == "verify":
        from pipeline.verify import run_verify
        rep, planted = run_verify(a.input, a.run, a.sample, a.budget_usd)
        print({"verified": rep["verified"], "agreement": rep["agreement"], "severity_mae": rep["severity_mae"],
               "planted_caught": f"{planted['caught']}/{planted['planted']}"})
    elif a.cmd == "rank":
        from pipeline.rank import build
        print(build(a.run, a.input))
    elif a.cmd == "group":
        from pipeline.group import run_group
        print(run_group(a.run, a.budget_usd))
    elif a.cmd == "memo":
        from pipeline.memo import run_memo
        print(run_memo(a.input, a.run, a.budget_usd))
    elif a.cmd == "grading":
        from pipeline.export import export_grading
        print(export_grading(a.input, a.run, extra_call_logs=a.extra_calls))
    elif a.cmd == "all":
        from pipeline.enrich import run_enrich, run_log
        from pipeline.export import export_grading
        from pipeline.group import run_group
        from pipeline.ingest import ingest
        from pipeline.memo import run_memo
        from pipeline.rank import build
        from pipeline.records import export_records
        from pipeline.verify import run_verify
        a.run.mkdir(parents=True, exist_ok=True)
        for stage, fn in (("ingest", lambda: ingest(a.input, a.run)),
                          ("enrich", lambda: run_enrich(a.input, a.run, budget_usd=a.budget_usd, workers=a.workers)),
                          ("records", lambda: export_records(a.input, a.run)),
                          ("verify", lambda: run_verify(a.input, a.run, a.verify_sample, a.budget_usd)[0]["agreement"]),
                          ("rank", lambda: build(a.run, a.input)),
                          ("group", lambda: run_group(a.run, a.budget_usd)),
                          ("memo", lambda: run_memo(a.input, a.run, a.budget_usd)["status"]),
                          ("grading", lambda: export_grading(a.input, a.run))):
            run_log(a.run, "stage_start", stage=stage)
            result = fn()
            run_log(a.run, "stage_stop", stage=stage, result=result if isinstance(result, (str, dict)) else str(result))
            print(f"[all] {stage} done")
    elif a.cmd == "slice":
        rows = read_source(a.input)[a.start:a.start + a.count]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {len(rows)} rows to {a.out}")


if __name__ == "__main__":
    main()
