"""Replace a quarantined record's reason with an analyst-reviewed, more precise one (no model calls).
The change is appended to run_log.jsonl with the old reason, so the edit stays auditable.

    .venv/bin/python tools/tag_quarantine.py runs/full <review_id> "<new reason>" "<evidence summary>"
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.enrich import run_log  # noqa: E402
from pipeline.io import now  # noqa: E402

run, rid, reason, evidence = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
db = sqlite3.connect(run / "state.sqlite", isolation_level=None)
row = db.execute("SELECT status, reason, attempts FROM records WHERE review_id=?", (rid,)).fetchone()
assert row and row[0] == "quarantined", f"{rid} is not quarantined: {row}"
attempts = int(sys.argv[5]) if len(sys.argv) > 5 else row[2]
db.execute("UPDATE records SET reason=?, attempts=?, updated_at=? WHERE review_id=?", (reason, attempts, now(), rid))
run_log(run, "quarantine_reason_updated", review_id=rid, old_reason=row[1], new_reason=reason, attempts=attempts,
        evidence=evidence, by="analyst review of calls.jsonl / invalid_items.jsonl")
print(f"{rid}: {row[1]!r} -> {reason!r} (attempts {attempts})")
