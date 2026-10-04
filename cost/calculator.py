"""100-review cost & runtime calculator (COST_CALCULATOR.md).

  python cost/calculator.py                 # default: OFFLINE replay -> cost/report.md (no API key, no calls)
  python cost/calculator.py measure         # offline: re-derive dev measurements from local runs/ logs
  python cost/calculator.py pilot --yes     # PAID: real cold + warm pilot on data/cost_100.csv

All money is computed as billed_units x price_per_unit from cost/usage.csv and cost/rates.csv, so editing a
rate changes the result linearly. Measured pilot numbers never depend on the projected record counts.
"""

import argparse
import csv
import json
import shutil
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COST = ROOT / "cost"
sys.path.insert(0, str(ROOT))

PILOT_INPUT = ROOT / "data" / "cost_100.csv"
PILOT_RUN = COST / "pilot_run"
PILOT_VERIFY_SAMPLE = 20
ITEMS = ("input_uncached", "input_cached", "output")


# ---------------------------------------------------------------- pricing core (pure arithmetic)
def load_rates():
    with (COST / "rates.csv").open(encoding="utf-8", newline="") as f:
        return {(r["model"], r["item"]): float(r["price_usd"]) / float(r["per_units"]) for r in csv.DictReader(f)}


def usage_rows_from_calls(calls, run_label):
    rows = []
    for c in calls:
        cached = c.get("cached_input_tokens", 0) or 0
        rows.append({"pilot_run": run_label, "request_id": c["request_id"], "stage": c["role"], "model": c["model"],
                     "reasoning_effort": c.get("reasoning_effort", ""), "outcome": c["outcome"],
                     "usage_known": c.get("usage_known", True), "review_ids": len(c["review_ids"]),
                     "input_uncached": c["input_tokens"] - cached, "input_cached": cached, "output": c["output_tokens"],
                     "reasoning_tokens_included_in_output": c.get("reasoning_tokens", 0), "latency_s": c.get("latency_s", 0)})
    return rows


def cost_of(row, rates):
    return sum(int(row[i]) * rates[(row["model"], i)] for i in ITEMS)


# ---------------------------------------------------------------- paid pilot
def run_pilot():
    from pipeline.enrich import run_enrich
    from pipeline.group import run_group
    from pipeline.ingest import ingest
    from pipeline.io import file_sha, read_json, read_jsonl
    from pipeline.memo import run_memo
    from pipeline.rank import build
    from pipeline.records import export_records
    from pipeline.verify import run_verify

    manifest = read_json(ROOT / "data" / "manifest.json")
    assert file_sha(PILOT_INPUT) == manifest["files"]["cost_100.csv"]["sha256"], "cost_100.csv checksum mismatch"
    if PILOT_RUN.exists():
        shutil.rmtree(PILOT_RUN)  # cold run starts from an empty result cache
    PILOT_RUN.mkdir(parents=True)
    budget = 0.25
    stages = [("ingest", lambda: ingest(PILOT_INPUT, PILOT_RUN)),
              ("enrich", lambda: run_enrich(PILOT_INPUT, PILOT_RUN, budget_usd=budget, workers=1)),
              ("records", lambda: export_records(PILOT_INPUT, PILOT_RUN)),
              ("verify", lambda: run_verify(PILOT_INPUT, PILOT_RUN, PILOT_VERIFY_SAMPLE, budget)),
              ("rank", lambda: build(PILOT_RUN, PILOT_INPUT)),
              ("group", lambda: run_group(PILOT_RUN, budget)),
              ("memo", lambda: run_memo(PILOT_INPUT, PILOT_RUN, budget))]
    timings = {}
    calls_path = PILOT_RUN / "calls.jsonl"
    for label in ("cold", "warm"):
        before = sum(1 for _ in calls_path.open()) if calls_path.exists() else 0
        t0 = time.time()
        per_stage = {}
        for name, fn in stages:
            s0 = time.time()
            fn()
            per_stage[name] = round(time.time() - s0, 3)
        timings[label] = {"wall_clock_s": round(time.time() - t0, 3), "stage_s": per_stage, "calls_from_line": before}
    calls = read_jsonl(calls_path)
    cold_calls = calls[:timings["warm"]["calls_from_line"]]
    warm_calls = calls[timings["warm"]["calls_from_line"]:]
    tagged = [{**c, "pilot_run": "cold"} for c in cold_calls] + [{**c, "pilot_run": "warm"} for c in warm_calls]
    with (COST / "pilot_calls.jsonl").open("w", encoding="utf-8") as f:
        for c in tagged:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    rows = usage_rows_from_calls(cold_calls, "cold") + usage_rows_from_calls(warm_calls, "warm")
    with (COST / "usage.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["pilot_run"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    shutil.copyfile(PILOT_RUN / "records.jsonl", COST / "pilot_records.jsonl")
    recs = read_jsonl(PILOT_RUN / "records.jsonl")
    sessions = sorted(PILOT_RUN.glob("enrich_session_*.json"))
    pilot = {"input": "data/cost_100.csv", "input_sha256": file_sha(PILOT_INPUT), "ids": [r["review_id"] for r in recs],
             "completed": sum(r["status"] == "completed" for r in recs), "quarantined": sum(r["status"] != "completed" for r in recs),
             "unique_texts": read_json(PILOT_RUN / "ingestion_report.json")["distinct_nonempty_texts"],
             "result_cache_hits_cold": sum(bool(r.get("cache_source_id")) for r in recs),
             "warm_enrich_calls": sum(c["role"] == "enrich" for c in warm_calls), "warm_total_calls": len(warm_calls),
             "enrich_sessions": [read_json(p) for p in sessions], "timings": timings, "workers": 1,
             "verify_sample": PILOT_VERIFY_SAMPLE, "ran_on": date.today().isoformat()}
    (COST / "pilot_summary.json").write_text(json.dumps(pilot, indent=2), encoding="utf-8")
    print(json.dumps({k: pilot[k] for k in ("completed", "quarantined", "warm_enrich_calls", "warm_total_calls")}))


# ---------------------------------------------------------------- offline: dev measurements from saved logs
def measure():
    from pipeline.io import read_json, read_jsonl
    out = {}
    for name in ("dev500_v3", "dev10k_v3", "diag2k_val2"):
        run = ROOT / "runs" / name
        if not (run / "calls.jsonl").exists():
            continue
        calls = [c for c in read_jsonl(run / "calls.jsonl") if c["role"] == "enrich"]
        sessions = [read_json(p) for p in sorted(run.glob("enrich_session_*.json"))]
        starts = [json.loads(l) for l in (run / "run_log.jsonl").open()] if (run / "run_log.jsonl").exists() else []
        workers = sorted({e["workers"] for e in starts if e.get("event") == "enrich_start"})
        timed = [s for s in sessions if s["originals_completed_this_session"]]
        out[name] = {"label_config": sessions[-1]["label_config"] if sessions else None,
                     "rows": sessions[-1]["rows"] if sessions else None,
                     "originals_completed": sum(s["originals_completed_this_session"] for s in sessions),
                     "enrich_calls": len(calls), "retry_calls": sum(c.get("enrich_attempt") == 2 for c in calls),
                     "failed_calls": sum(c["outcome"] == "failed" for c in calls),
                     "input_uncached": sum(c["input_tokens"] - (c.get("cached_input_tokens") or 0) for c in calls),
                     "input_cached": sum(c.get("cached_input_tokens") or 0 for c in calls),
                     "output": sum(c["output_tokens"] for c in calls), "model": "gpt-6-luna",
                     "enrich_elapsed_s": round(sum(s["elapsed_s"] for s in timed), 1), "workers": workers}
    (COST / "dev_measurements.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote cost/dev_measurements.json ({', '.join(out)})")


# ---------------------------------------------------------------- offline replay + estimates
def replay():
    rates = load_rates()
    with (COST / "usage.csv").open(encoding="utf-8", newline="") as f:
        usage = list(csv.DictReader(f))
    a = json.loads((COST / "assumptions.json").read_text())
    pilot = json.loads((COST / "pilot_summary.json").read_text())
    dev = json.loads((COST / "dev_measurements.json").read_text())

    def stage_table(run):
        t = {}
        for r in usage:
            if r["pilot_run"] != run:
                continue
            s = t.setdefault(r["stage"], {"requests": 0, "failed": 0, "input_uncached": 0, "input_cached": 0, "output": 0, "cost": 0.0})
            s["requests"] += 1
            s["failed"] += r["outcome"] == "failed"
            for i in ITEMS:
                s[i] += int(r[i])
            s["cost"] += cost_of(r, rates)
        return t

    cold, warm = stage_table("cold"), stage_table("warm")
    cold_total, warm_total = sum(s["cost"] for s in cold.values()), sum(s["cost"] for s in warm.values())

    # Per-unit enrichment cost from each measurement (same arithmetic as the pilot).
    def per_original(m):
        c = sum(m[i] * rates[(m["model"], i)] for i in ITEMS)
        return c / m["originals_completed"], c
    measurements = [("pilot cold (100 rows)", cold.get("enrich", {}).get("cost", 0) / max(1, pilot["unique_texts"]), pilot["unique_texts"])]
    for name, m in dev.items():
        if m["originals_completed"]:
            u, _ = per_original(m)
            measurements.append((f"{name} ({m['rows']} rows, {m['label_config']})", u, m["originals_completed"]))
    base_unit = next(u for n, u, k in measurements if n.startswith(a["base_case_measurement"]))
    worst_unit = max(u for _, u, _ in measurements)

    full = a["full_run"]
    verify_unit = cold.get("verify", {}).get("cost", 0) / max(1, pilot["verify_sample"])
    group_fixed = cold.get("group", {}).get("cost", 0) / max(1, cold.get("group", {}).get("requests", 1)) * full["group_issue_calls"]
    memo_fixed = cold.get("memo", {}).get("cost", 0) * full["memo_calls"]

    def scenario(unit, retry_margin, verify_n):
        enrich = unit * full["distinct_nonempty_texts"] * (1 + retry_margin)
        verify = verify_unit * verify_n * (1 + retry_margin)
        return {"enrich": enrich, "verify": verify, "group": group_fixed, "memo": memo_fixed * (1 + retry_margin),
                "total": enrich + verify + group_fixed + memo_fixed * (1 + retry_margin)}
    base = scenario(base_unit, a["base_retry_margin"], full["verify_sample"])
    cons = scenario(worst_unit, a["conservative_retry_margin"], full["verify_sample_conservative"])
    no_reuse = base_unit * full["nonempty_rows"] * (1 + a["base_retry_margin"])

    # Runtime: measured throughput at the chosen worker count, capped by the provider token-rate limit.
    d = dev[a["throughput_measurement"]]
    thr = d["originals_completed"] / d["enrich_elapsed_s"]
    tokens_per_original = (d["input_uncached"] + d["input_cached"] + d["output"]) / d["originals_completed"]
    reserved_per_call = a["avg_input_tokens_per_call"] + a["max_output_tokens"]
    tpm_cap_originals_per_s = a["provider_tpm_limit"] / reserved_per_call * 50 / 60
    scaled = thr * a["chosen_workers"] / max(d["workers"] or [1])
    eff = min(scaled, tpm_cap_originals_per_s)
    hours = full["distinct_nonempty_texts"] / eff / 3600

    budget = a["budget_usd"]
    L = []
    L.append("# Cost & runtime calculator — report\n")
    L.append(f"Generated offline from saved files on {date.today().isoformat()}. No API key or model call is needed to reproduce it: "
             "`python cost/calculator.py`.\n")
    L.append("## 1. Measured: 100-review pilot (`data/cost_100.csv`)\n")
    L.append(f"- Input SHA-256 `{pilot['input_sha256']}` (matches manifest); {len(pilot['ids'])} IDs; "
             f"completed **{pilot['completed']}**, quarantined/failed **{pilot['quarantined']}**; unique texts {pilot['unique_texts']}; "
             f"result-cache hits in cold run {pilot['result_cache_hits_cold']}.")
    L.append(f"- Workers: {pilot['workers']}; verification sample: {pilot['verify_sample']} reviews; run date {pilot['ran_on']}.")
    L.append(f"- Wall clock: cold **{pilot['timings']['cold']['wall_clock_s']} s**, warm **{pilot['timings']['warm']['wall_clock_s']} s**. "
             f"Warm run: **{pilot['warm_enrich_calls']} enrichment calls**, {pilot['warm_total_calls']} calls in total.\n")
    L.append("| run | stage | model / effort | requests | failed | input uncached | input cached | output | cost (USD) | stage time (s) |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    effort = {r["stage"]: f"{r['model']} / {r['reasoning_effort']}" for r in usage}
    for run, table in (("cold", cold), ("warm", warm)):
        for st in ("enrich", "verify", "group", "memo"):
            s = table.get(st)
            secs = pilot["timings"][run]["stage_s"].get(st, 0)
            if s:
                L.append(f"| {run} | {st} | {effort.get(st, '')} | {s['requests']} | {s['failed']} | {s['input_uncached']} | {s['input_cached']} | {s['output']} | {s['cost']:.6f} | {secs} |")
            else:
                L.append(f"| {run} | {st} | — | 0 | 0 | 0 | 0 | 0 | 0.000000 | {secs} |")
    L.append(f"\n**Cold total ${cold_total:.6f}** (${cold_total / 100 * 1000:.4f} per 1,000 input rows; "
             f"${cold_total / max(1, pilot['completed']):.7f} per completed record). **Warm incremental total ${warm_total:.6f}.**")
    L.append("Code-only stages (ingest, records, rank) have no API charge; local compute is a laptop and is **not measured** "
             "(reported as unknown, not zero).\n")
    L.append("## 2. Measured: development checkpoints (same arithmetic)\n")
    L.append("| measurement | originals classified | enrichment cost per original (USD) |")
    L.append("|---|---:|---:|")
    for n, u, k in measurements:
        L.append(f"| {n} | {k} | {u:.8f} |")
    L.append("\n## 3. Estimated: full run (660,622 rows)\n")
    L.append(f"All 660,622 rows accounted for; {full['nonempty_rows']:,} nonempty outputs; {full['empty_rows']} empty-text quarantines. "
             f"With exact-text reuse only {full['distinct_nonempty_texts']:,} distinct texts need model calls.\n")
    L.append("| scenario | enrichment | verification | grouping | memo | **total** |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for name, sc in ((f"base ({a['base_case_measurement']}, +{int(a['base_retry_margin']*100)}% retries)", base),
                     (f"conservative (worst measured unit, +{int(a['conservative_retry_margin']*100)}% retries, larger verify sample)", cons)):
        L.append(f"| {name} | ${sc['enrich']:.2f} | ${sc['verify']:.2f} | ${sc['group']:.3f} | ${sc['memo']:.3f} | **${sc['total']:.2f}** |")
    L.append(f"\nNo-reuse comparison (classify all {full['nonempty_rows']:,} nonempty rows): enrichment ≈ **${no_reuse:.2f}**.\n")
    L.append(f"Runtime: measured {thr:.2f} originals/s at {max(d["workers"] or [1])} workers ({a["throughput_measurement"]}); "
             f"scaled to {a['chosen_workers']} workers ≈ {scaled:.2f}/s; provider limit {a['provider_tpm_limit']:,} TPM with "
             f"{reserved_per_call:,} tokens reserved per call caps throughput at ≈ {tpm_cap_originals_per_s:.2f}/s. "
             f"Estimated enrichment time ≈ **{hours:.1f} h** (one-time stage overheads add minutes).\n")
    L.append("## 4. Controls and decision\n")
    L.append(f"- Budget (editable in `cost/assumptions.json`): **${budget:.2f}**; per-call output cap {a['max_output_tokens']:,} tokens; "
             f"max concurrency {a['chosen_workers']}; stronger-model fallback fraction {a['max_fallback_fraction']} (none used).")
    for name, sc in (("base", base), ("conservative", cons)):
        if sc["total"] > budget:
            L.append(f"- ⚠️ **WARNING: the {name} scenario (${sc['total']:.2f}) exceeds the ${budget:.2f} budget.**")
    if max(base["total"], cons["total"]) <= budget:
        L.append(f"- Both scenarios are within budget. Decision: run the full corpus at {a['chosen_workers']} workers with a "
                 f"${budget:.2f} code cap, plus the OpenAI project hard limit as a backstop.")
    L.append("\n## 5. Rates used\n")
    with (COST / "rates.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            L.append(f"- {r['model']} {r['item']}: ${r['price_usd']} per {int(float(r['per_units'])):,} {r['unit']} — [{r['source']}]({r['source']}) (checked {r['checked']})")
    L.append("\nFormula: `item_cost = billed_units × price_per_unit`; `total = Σ item_cost`. Cached input is subtracted from input "
             "before the uncached rate is applied; reasoning tokens are already inside billed output and are not added again. "
             "Batch-API discounts are not applied (standard tier was used).")
    (COST / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[-25:]) if False else f"wrote cost/report.md  base ${base['total']:.2f}  conservative ${cons['total']:.2f}  ~{hours:.1f} h")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", nargs="?", default="replay", choices=["replay", "measure", "pilot"])
    p.add_argument("--yes", action="store_true", help="confirm a PAID pilot run")
    a = p.parse_args()
    if a.cmd == "pilot":
        if not a.yes:
            sys.exit("The pilot makes real paid API calls (about $0.01). Re-run with --yes to confirm.")
        run_pilot()
        measure()
        replay()
    elif a.cmd == "measure":
        measure()
    else:
        replay()


if __name__ == "__main__":
    main()
