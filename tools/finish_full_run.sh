#!/bin/zsh
# Everything after full-corpus enrichment. Model stages here are small (verify 1,000; 15 naming calls; memo).
# Usage: zsh tools/finish_full_run.sh
set -eu
cd "$(dirname "$0")/.."
PY=.venv/bin/python
IN=data/spotify_reviews_18months.csv
RUN=runs/full
CAP=25

# Mop-up: retry any originals left pending by transient API failures (resume phase, same settings), at most twice.
for i in 1 2; do
  PENDING=$($PY -c "
from pipeline.enrich import State; from pipeline.io import read_source
s=State('$RUN/state.sqlite').all(); seen=set(); n=0
for r in read_source('$IN'):
    t=r['review_text']
    if t.strip() and t not in seen:
        seen.add(t); n += r['review_id'] not in s
print(n)")
  echo "pending originals: $PENDING"
  [ "$PENDING" = "0" ] && break
  $PY run.py enrich --input $IN --run $RUN --budget-usd $CAP --workers 4 >> $RUN/enrich_stdout.log 2>&1
done

$PY run.py records --input $IN --run $RUN
$PY run.py verify  --input $IN --run $RUN --sample 1000 --budget-usd $CAP
$PY run.py rank    --input $IN --run $RUN
$PY run.py group   --run $RUN --budget-usd $CAP
$PY run.py memo    --input $IN --run $RUN --budget-usd $CAP
$PY run.py grading --input $IN --run $RUN
$PY -c "from pipeline.summary import summarize; import json; s=summarize('$RUN', ['taxonomy/discovery_v1/calls.jsonl']); print(json.dumps({k: s[k] for k in ('records','total_cost_usd_measured')}))"

# Zero-API self-check (reports kept outside grading/).
mkdir -p evals/checker
$PY vendor/check_submission.py reference --full $IN --analysis $IN --out evals/checker/local-reference.json
$PY vendor/check_submission.py check --reference evals/checker/local-reference.json --submission $RUN/grading --out evals/checker/self-check.json
$PY evals/golden_eval.py $RUN
$PY vendor/check_submission.py check --reference evals/checker/local-reference.json --gold evals/golden_benchmark.json --submission $RUN/grading --out evals/checker/self-check-with-golden.json
$PY -c "import json; r=json.load(open('evals/checker/self-check.json')); print(r['status'], r['working_coverage_point_candidate'], r['issue_counts'])"
echo FINISHED
