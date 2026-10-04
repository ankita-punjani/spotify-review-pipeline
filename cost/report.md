# Cost & runtime calculator — report

Generated offline from saved files on 2026-10-04. No API key or model call is needed to reproduce it: `python cost/calculator.py`.

## 1. Measured: 100-review pilot (`data/cost_100.csv`)

- Input SHA-256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` (matches manifest); 100 IDs; completed **100**, quarantined/failed **0**; unique texts 100; result-cache hits in cold run 0.
- Workers: 1; verification sample: 20 reviews; run date 2026-10-04.
- Wall clock: cold **87.732 s**, warm **0.041 s**. Warm run: **0 enrichment calls**, 0 calls in total.

| run | stage | model / effort | requests | failed | input uncached | input cached | output | cost (USD) | stage time (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| cold | enrich | gpt-6-luna / none | 2 | 0 | 6281 | 2564 | 4770 | 0.003039 | 29.286 |
| cold | verify | gpt-6-luna / low | 2 | 0 | 1569 | 0 | 1029 | 0.000671 | 9.373 |
| cold | group | gpt-6-luna / low | 15 | 0 | 5557 | 0 | 830 | 0.000971 | 24.589 |
| cold | memo | gpt-6-luna / medium | 1 | 0 | 6485 | 0 | 2446 | 0.001871 | 24.458 |
| warm | enrich | — | 0 | 0 | 0 | 0 | 0 | 0.000000 | 0.012 |
| warm | verify | — | 0 | 0 | 0 | 0 | 0 | 0.000000 | 0.005 |
| warm | group | — | 0 | 0 | 0 | 0 | 0 | 0.000000 | 0.004 |
| warm | memo | — | 0 | 0 | 0 | 0 | 0 | 0.000000 | 0.005 |

**Cold total $0.006552** ($0.0655 per 1,000 input rows; $0.0000655 per completed record). **Warm incremental total $0.000000.**
Code-only stages (ingest, records, rank) have no API charge; local compute is a laptop and is **not measured** (reported as unknown, not zero).

## 2. Measured: development checkpoints (same arithmetic)

| measurement | originals classified | enrichment cost per original (USD) |
|---|---:|---:|
| pilot cold (100 rows) | 100 | 0.00003039 |
| dev500_v3 (500 rows, gpt-6-luna+enrich_v3+schema_v2+effort-none) | 478 | 0.00002989 |
| dev10k_v3 (10000 rows, gpt-6-luna+enrich_v3+schema_v2+effort-none) | 7098 | 0.00003778 |
| diag2k_val2 (2000 rows, gpt-6-luna+enrich_v3+schema_v2+effort-none+val2) | 1771 | 0.00002885 |

## 3. Estimated: full run (660,622 rows)

All 660,622 rows accounted for; 660,609 nonempty outputs; 13 empty-text quarantines. With exact-text reuse only 484,189 distinct texts need model calls.

| scenario | enrichment | verification | grouping | memo | **total** |
|---|---:|---:|---:|---:|---:|
| base (diag2k_val2, +5% retries) | $14.67 | $0.04 | $0.001 | $0.004 | **$14.71** |
| conservative (worst measured unit, +25% retries, larger verify sample) | $22.87 | $0.08 | $0.001 | $0.005 | **$22.96** |

No-reuse comparison (classify all 660,609 nonempty rows): enrichment ≈ **$20.01**.

Runtime: measured 14.47 originals/s at [4] workers (diag2k_val2); scaled to 10 workers ≈ 36.17/s; provider limit 500,000 TPM with 10,500 tokens reserved per call caps throughput at ≈ 39.68/s. Estimated enrichment time ≈ **3.7 h** (one-time stage overheads add minutes).

## 4. Controls and decision

- Budget (editable in `cost/assumptions.json`): **$35.00**; per-call output cap 7,000 tokens; max concurrency 10; stronger-model fallback fraction 0.0 (none used).
- Both scenarios are within budget. Decision: run the full corpus at 10 workers with a $35.00 code cap, plus the OpenAI project hard limit as a backstop.

## 5. Rates used

- gpt-6-luna input_uncached: $0.10 per 1,000,000 tokens — [https://developers.openai.com/api/docs/models/gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna) (checked 2026-10-03)
- gpt-6-luna input_cached: $0.01 per 1,000,000 tokens — [https://developers.openai.com/api/docs/models/gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna) (checked 2026-10-03)
- gpt-6-luna output: $0.50 per 1,000,000 tokens — [https://developers.openai.com/api/docs/models/gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna) (checked 2026-10-03)

Formula: `item_cost = billed_units × price_per_unit`; `total = Σ item_cost`. Cached input is subtracted from input before the uncached rate is applied; reasoning tokens are already inside billed output and are not added again. Batch-API discounts are not applied (standard tier was used).
