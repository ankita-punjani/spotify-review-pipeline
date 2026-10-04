#!/bin/zsh
# Full-corpus run with a recorded interruption and resume (GRADING_CONTRACT: checkpoint_before/after).
# Usage: zsh tools/resume_demo.sh   (from the repo root)
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
IN=data/spotify_reviews_18months.csv
RUN=runs/full
CAP=25
W=10
mkdir -p $RUN

echo "=== 1. Ingest all 660,622 rows (code only, no model calls) ==="
$PY run.py ingest --input $IN --run $RUN

echo; echo "=== 2. Enrichment, initial phase ($W workers, \$$CAP cap) - will be interrupted after 90 s ==="
$PY run.py enrich --input $IN --run $RUN --budget-usd $CAP --workers $W >> $RUN/enrich_stdout.log 2>&1 &
PID=$!
for i in 1 2 3 4 5 6; do sleep 15; tail -n 1 $RUN/run_log.jsonl | cut -c1-170; done
echo; echo ">>> INTERRUPT: sending Ctrl-C (SIGINT) to enrichment process $PID"
kill -INT $PID
wait $PID
tail -n 1 $RUN/enrich_stdout.log | cut -c1-300

echo; echo "=== 3. Saved state after the interruption ==="
$PY run.py checkpoint --run $RUN --out $RUN/checkpoint_before.json
sqlite3 $RUN/state.sqlite "SELECT status, COUNT(*) FROM records GROUP BY status"

echo; echo "=== 4. Resume with unchanged settings ==="
nohup $PY run.py enrich --input $IN --run $RUN --budget-usd $CAP --workers $W >> $RUN/enrich_stdout.log 2>&1 &
RPID=$!
caffeinate -i -w $RPID &
sleep 5; grep enrich_start $RUN/run_log.jsonl | tail -n 1 | cut -c1-330
sleep 70
$PY run.py checkpoint --run $RUN --out $RUN/checkpoint_after.json

echo; echo "=== 5. Resume evidence ==="
$PY tools/resume_check.py $RUN

echo; echo "Resume (pid $RPID) keeps running in the background with the Mac kept awake."
echo "Progress: tail -f $RUN/run_log.jsonl"
