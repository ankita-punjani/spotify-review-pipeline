"""Stage 2 — Enrich. Code owns batching, dedupe, state, validation and accounting; the model reads text."""

import json
import signal
import sqlite3
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from .io import ROOT, now, read_source, row_sha, write_json
from .labels import SCHEMA_VERSION, batch_schema, needs_quote, validate
from .llm import LLM, BudgetStop, Ledger

PROMPT_VERSION = "enrich_v3"
MODEL = "gpt-6-luna"
EFFORT = "none"
VALIDATOR_VERSION = "val2"  # val2: empty-quote fallback, fuzzy repair, output salvage
LABEL_CONFIG = f"{MODEL}+{PROMPT_VERSION}+{SCHEMA_VERSION}+effort-{EFFORT}+{VALIDATOR_VERSION}"
MAX_BATCH = 50
STALL_SECONDS = 300
MAX_OUTPUT_TOKENS = 7000  # ~50 items x ~55 tokens = ~2,750 typical; a cut-off response keeps its complete items


class State:
    """Durable per-run state in SQLite. Every write commits immediately (atomic per batch)."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.Lock()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records(
              review_id TEXT PRIMARY KEY, source_sha256 TEXT, status TEXT, label_config TEXT,
              fields TEXT, notes TEXT, cache_source_id TEXT, attempts INTEGER DEFAULT 0,
              reason TEXT, phase TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS sessions(
              session INTEGER PRIMARY KEY AUTOINCREMENT, phase TEXT, started_at TEXT, ended_at TEXT,
              completed_before INTEGER, completed_after INTEGER, stop_reason TEXT);
        """)

    def put(self, rows):
        with self.lock:
            self.db.execute("BEGIN")
            self.db.executemany(
                "INSERT OR REPLACE INTO records VALUES (:review_id,:source_sha256,:status,:label_config,:fields,"
                ":notes,:cache_source_id,:attempts,:reason,:phase,:updated_at)", rows)
            self.db.execute("COMMIT")

    def all(self):
        with self.lock:
            cur = self.db.execute("SELECT * FROM records")
            cols = [c[0] for c in cur.description]
            return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}

    def completed_ids(self):
        with self.lock:
            return sorted(r[0] for r in self.db.execute("SELECT review_id FROM records WHERE status='completed'"))

    def session_start(self, phase, completed):
        with self.lock:
            return self.db.execute("INSERT INTO sessions(phase,started_at,completed_before) VALUES (?,?,?)",
                                   (phase, now(), completed)).lastrowid

    def session_end(self, sid, completed, reason):
        with self.lock:
            self.db.execute("UPDATE sessions SET ended_at=?, completed_after=?, stop_reason=? WHERE session=?",
                            (now(), completed, reason, sid))

    def sessions(self):
        with self.lock:
            cur = self.db.execute("SELECT * FROM sessions ORDER BY session")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def _record(rid, sha, status, phase, fields=None, notes=None, cache=None, attempts=0, reason=None):
    return {"review_id": rid, "source_sha256": sha, "status": status, "label_config": LABEL_CONFIG,
            "fields": json.dumps(fields, ensure_ascii=False) if fields else None,
            "notes": json.dumps(notes) if notes else None, "cache_source_id": cache, "attempts": attempts,
            "reason": reason, "phase": phase, "updated_at": now()}


def run_log(run_dir, event, **data):
    """Append one structured event to run_log.jsonl (stage starts/stops, progress, stops)."""
    with (Path(run_dir) / "run_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now(), "event": event, **data}, ensure_ascii=False) + "\n")


TRANSIENT_RESCUE_PREFIX = "invalid_after_retry:call_failed|"


def run_enrich(input_csv, run_dir, *, budget_usd, workers=1, max_batches=None, batch_size=MAX_BATCH, log=print,
               rescue_transient=False):
    """rescue_transient: requeue quarantined originals whose FIRST attempt was a transient API failure
    (so only one invalid-output attempt has been used) for one more attempt. Off by default."""
    import faulthandler
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    faulthandler.register(signal.SIGUSR1, file=(run_dir / "thread_dump.txt").open("a"), all_threads=True)
    assert 1 <= batch_size <= MAX_BATCH
    instructions = (ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    schema = batch_schema()

    rows = read_source(input_csv)
    state = State(run_dir / "state.sqlite")
    existing = state.all()
    sha = {r["review_id"]: row_sha(r) for r in rows}
    text = {r["review_id"]: r["review_text"] for r in rows}

    # Exact-text groups: the first ID in file order is the original that gets a model call.
    groups = {}
    for r in rows:
        if r["review_text"].strip():
            groups.setdefault(r["review_text"], []).append(r["review_id"])

    done_prior = sum(1 for v in existing.values() if v["status"] == "completed" and v["label_config"] == LABEL_CONFIG)
    phase = "resume" if done_prior else "initial"
    sid = state.session_start(phase, done_prior)

    empties = [_record(r["review_id"], sha[r["review_id"]], "quarantined", phase, reason="empty_review_text")
               for r in rows if not r["review_text"].strip() and r["review_id"] not in existing]
    if empties:
        state.put(empties)

    def finished(rid):
        rec = existing.get(rid)
        if rescue_transient and rec and rec["status"] == "quarantined" and (rec["reason"] or "").startswith(TRANSIENT_RESCUE_PREFIX):
            return False
        return rec and rec["label_config"] == LABEL_CONFIG and rec["status"] in ("completed", "quarantined")

    pending = [ids[0] for ids in groups.values() if not finished(ids[0])]
    batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
    if max_batches is not None:
        batches = batches[:max_batches]
    run_log(run_dir, "enrich_start", session=sid, phase=phase, label_config=LABEL_CONFIG, input=str(input_csv),
            rows=len(rows), distinct_nonempty=len(groups), already_completed=done_prior, pending_originals=len(pending),
            batches=len(batches), workers=workers, budget_usd=budget_usd)
    log(f"[enrich] {len(rows)} rows | {len(groups)} distinct nonempty texts | already done {done_prior} | "
        f"pending originals {len(pending)} | dispatching {len(batches)} batches | phase={phase} | {LABEL_CONFIG}")

    ledger = Ledger(budget_usd, run_dir / "spend.json")
    llm = LLM(MODEL, EFFORT, ledger, run_dir / "calls.jsonl", run_dir.name)
    stop = threading.Event()
    stop_reason = ["completed"]

    def on_sigint(*_):
        stop.set()
        stop_reason[0] = "interrupted"
        log("[enrich] interrupt received: finishing in-flight batches, then saving and exiting")
    old_handler = signal.signal(signal.SIGINT, on_sigint)

    invalid_log, invalid_lock = [], threading.Lock()

    def flush_invalid():
        with invalid_lock:
            if invalid_log:
                with (run_dir / "invalid_items.jsonl").open("a", encoding="utf-8") as f:
                    for x in invalid_log:
                        f.write(json.dumps(x, ensure_ascii=False) + "\n")
                invalid_log.clear()

    def call(ids, attempt):
        items = [{"i": n, "q": int(needs_quote(text[rid])), "t": text[rid]} for n, rid in enumerate(ids, 1)]
        payload = json.dumps({"reviews": items}, ensure_ascii=False)
        out = llm.call(role="enrich", instructions=instructions, payload=payload, schema=schema,
                       schema_name="enrichment", review_ids=ids, phase=phase, label_config=LABEL_CONFIG,
                       max_output_tokens=MAX_OUTPUT_TOKENS, prompt_version=PROMPT_VERSION,
                       extra={"enrich_attempt": attempt})
        if out is None:
            return {}, {rid: "call_failed" for rid in ids}
        good, bad, seen = {}, {}, set()
        for item in out.get("results", []):
            n = item.get("i")
            if type(n) is not int or not 1 <= n <= len(ids) or n in seen:
                continue  # foreign or duplicate index: ignored, the real ID is caught as missing below
            seen.add(n)
            rid = ids[n - 1]
            fields, info = validate(item, text[rid], final_attempt=(attempt == 2))
            if fields is None:
                bad[rid] = info
                invalid_log.append({"review_id": rid, "attempt": attempt, "reason": info, "model_item": item})
            else:
                good[rid] = (fields, info)
        for n, rid in enumerate(ids, 1):
            if n not in seen:
                bad[rid] = "missing_from_output"
        return good, bad

    def work(ids):
        good, bad = call(ids, 1)
        flush_invalid()
        out = [_record(rid, sha[rid], "completed", phase, f, notes, attempts=1) for rid, (f, notes) in good.items()]
        if out:
            state.put(out)  # saved before any retry, so a later stop cannot lose paid work
        if bad and not stop.is_set():
            # One retry for invalid/missing items only, then quarantine with the reason.
            # A whole-batch failure is retried as two halves so one problem review cannot sink all 50 again.
            retry = list(bad)
            if len(retry) > 1 and all(v == "call_failed" for v in bad.values()):
                (g1, b1), (g2, b2) = call(retry[:len(retry) // 2], 2), call(retry[len(retry) // 2:], 2)
                good2, bad2 = {**g1, **g2}, {**b1, **b2}
            else:
                good2, bad2 = call(retry, 2)
            out2 = [_record(rid, sha[rid], "completed", phase, f, notes + [f"first_attempt_invalid:{bad[rid]}"], attempts=2)
                    for rid, (f, notes) in good2.items()]
            for rid, why in bad2.items():
                if why == "call_failed":
                    continue  # transient API failure: stays pending for the next run
                out2.append(_record(rid, sha[rid], "quarantined", phase, attempts=2,
                                    reason=f"invalid_after_retry:{bad[rid]}|{why}"))
            if out2:
                state.put(out2)
            out += out2
            flush_invalid()
        return sum(r["status"] == "completed" for r in out), len(bad)

    started, completed_now, invalid_first, last_logged = time.time(), 0, 0, [-1]
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            queue, inflight = list(batches), set()
            while (queue or inflight):
                while queue and len(inflight) < workers and not stop.is_set():
                    inflight.add(pool.submit(work, queue.pop(0)))
                if not inflight:
                    break
                done, inflight = wait(inflight, timeout=STALL_SECONDS, return_when=FIRST_COMPLETED)
                if not done:
                    faulthandler.dump_traceback(file=(run_dir / "thread_dump.txt").open("a"), all_threads=True)
                    run_log(run_dir, "enrich_stall", session=sid, inflight=len(inflight), seconds=STALL_SECONDS)
                    log(f"[enrich] no batch finished in {STALL_SECONDS}s; thread dump written")
                for fut in done:
                    try:
                        c, b = fut.result()
                        completed_now += c
                        invalid_first += b
                    except BudgetStop as e:
                        stop.set()
                        stop_reason[0] = f"budget_stop: {e}"
                        log(f"[enrich] {stop_reason[0]}")
                n_done = len(batches) - len(queue) - len(inflight)
                if n_done != last_logged[0] and (n_done % 10 == 0 or (not queue and not inflight)):
                    last_logged[0] = n_done
                    run_log(run_dir, "enrich_progress", session=sid, batches_done=n_done, batches=len(batches),
                            completed_this_session=completed_now, spent_usd=round(ledger.spent, 6))
                    log(f"[enrich] batches {n_done}/{len(batches)} | originals completed this session {completed_now} | "
                        f"spent ${ledger.spent:.4f} | {time.time() - started:.0f}s")
    finally:
        signal.signal(signal.SIGINT, old_handler)

    # Exact-text reuse: duplicates copy the original's validated fields and cite it directly.
    current = state.all()
    reuse = []
    for ids in groups.values():
        orig = current.get(ids[0])
        if not orig or orig["status"] != "completed" or orig["label_config"] != LABEL_CONFIG:
            continue
        for rid in ids[1:]:
            have = current.get(rid)
            if have and have["status"] == "completed" and have["label_config"] == LABEL_CONFIG:
                continue
            reuse.append(_record(rid, sha[rid], "completed", phase, json.loads(orig["fields"]),
                                 json.loads(orig["notes"]) if orig["notes"] else None, cache=ids[0]))
    if reuse:
        state.put(reuse)

    completed_total = len(state.completed_ids())
    state.session_end(sid, completed_total, stop_reason[0])
    summary = {"stage": "enrich", "session": sid, "phase": phase, "label_config": LABEL_CONFIG,
               "input": str(input_csv), "rows": len(rows), "distinct_nonempty": len(groups),
               "batches_dispatched": len(batches), "originals_completed_this_session": completed_now,
               "first_attempt_invalid_items": invalid_first, "cache_reuse_written": len(reuse),
               "completed_total": completed_total, "spent_usd_total": round(ledger.spent, 6),
               "elapsed_s": round(time.time() - started, 1), "stop_reason": stop_reason[0], "ended_at": now()}
    write_json(run_dir / f"enrich_session_{sid}.json", summary)
    run_log(run_dir, "enrich_stop", **summary)
    log(f"[enrich] done: {json.dumps(summary)}")
    return summary


def snapshot(run_dir, out_path):
    ids = State(Path(run_dir) / "state.sqlite").completed_ids()
    write_json(out_path, {"completed_ids": ids, "count": len(ids), "taken_at": now()})
    return len(ids)
