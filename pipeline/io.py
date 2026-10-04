"""Shared file helpers. Row hashing and CSV parsing come from the course checker so they match exactly."""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "vendor"))
import check_submission as cs  # noqa: E402

FIELDS = cs.FIELDS
TOPICS = cs.TOPICS
INTENTS = cs.INTENTS
row_sha = cs.row_sha
file_sha = cs.sha
csv_rows = cs.csv_rows


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_source(path):
    """Read every CSV row (quoted multiline text handled by the csv module), keeping the six source fields only."""
    return [{k: row[k] for k in FIELDS} for row in csv_rows(path)]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
