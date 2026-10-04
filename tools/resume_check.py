"""Print interruption/resume evidence for a run: checkpoint sizes, sessions, and proof that resume calls
never resent an ID completed before the interruption. Reads saved files only."""

import json
import sqlite3
import sys
from pathlib import Path

run = Path(sys.argv[1])
before = set(json.loads((run / "checkpoint_before.json").read_text())["completed_ids"])
after_path = run / "checkpoint_after.json"
after = set(json.loads(after_path.read_text())["completed_ids"]) if after_path.exists() else set()
calls = [json.loads(l) for l in (run / "calls.jsonl").open()]
enrich = [c for c in calls if c["role"] == "enrich"]
resume = [c for c in enrich if c["phase"] == "resume"]
resent = {rid for c in resume for rid in c["review_ids"]} & before
print(f"checkpoint_before: {len(before):,} completed IDs")
if after:
    print(f"checkpoint_after:  {len(after):,} completed IDs  (+{len(after - before):,} new; before is a subset of after: {before <= after})")
print(f"enrichment calls: {sum(c['phase'] == 'initial' for c in enrich)} initial, {len(resume)} resume")
print(f"IDs from checkpoint_before re-sent in resume calls: {len(resent)}")
db = sqlite3.connect(run / "state.sqlite")
for row in db.execute("SELECT session, phase, started_at, ended_at, completed_before, completed_after, stop_reason FROM sessions"):
    print("session", row)
