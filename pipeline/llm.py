"""Model-call wrapper: one place for spend control, bounded retries, and the call log."""

import json
import os
import random
import threading
import time
import uuid
from pathlib import Path

from .io import ROOT, now

# USD per 1M tokens, standard tier. Source: https://developers.openai.com/api/docs/models/gpt-6-luna (checked 2026-10-03).
# cost/rates.csv holds the editable copy used by the calculator.
RATES = {"gpt-6-luna": {"input": 0.10, "cached_input": 0.01, "output": 0.50}}
TRANSIENT_ATTEMPTS = 4  # per request, for rate limits / 5xx / timeouts


def salvage_results(raw):
    """Recover complete items from a truncated or junk-suffixed {"results":[...]} response.
    Every recovered item is still validated by the caller; nothing is invented."""
    start = raw.find('"results"')
    start = raw.find("[", start) if start >= 0 else -1
    if start < 0:
        return []
    dec, pos, items = json.JSONDecoder(), start + 1, []
    while True:
        while pos < len(raw) and raw[pos] in " \n\r\t,":
            pos += 1
        if pos >= len(raw) or raw[pos] != "{":
            break
        try:
            obj, pos = dec.raw_decode(raw, pos)
        except ValueError:
            break
        items.append(obj)
    return items


class BudgetStop(Exception):
    """The local spend cap (or the provider quota) would be exceeded; stop admitting work."""


def call_cost(model, input_tokens, cached_tokens, output_tokens):
    r = RATES[model]
    return ((input_tokens - cached_tokens) * r["input"] + cached_tokens * r["cached_input"]
            + output_tokens * r["output"]) / 1_000_000


class Ledger:
    """Shared spend ledger: reserve worst-case cost before dispatch, settle with actual usage after."""

    def __init__(self, cap_usd, path):
        self.cap = cap_usd
        self.path = Path(path)
        self.lock = threading.Lock()
        self.reserved = 0.0
        self.spent = 0.0
        if self.path.exists():
            self.spent = json.loads(self.path.read_text())["spent_usd"]

    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount > self.cap:
                raise BudgetStop(f"cap ${self.cap:.2f}: spent ${self.spent:.4f} + reserved ${self.reserved:.4f} + next ${amount:.4f}")
            self.reserved += amount

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual
            self.path.write_text(json.dumps({"spent_usd": round(self.spent, 6), "cap_usd": self.cap, "updated_at": now()}))


class LLM:
    def __init__(self, model, effort, ledger, calls_path, run_id):
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv(ROOT / ".env")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is not set (copy .env.example to .env).")
        self.client = OpenAI(max_retries=0, timeout=90.0)
        self.model, self.effort, self.ledger, self.run_id = model, effort, ledger, run_id
        self.calls_path = Path(calls_path)
        self.log_lock = threading.Lock()

    def _log(self, entry):
        with self.log_lock, self.calls_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def call(self, *, role, instructions, payload, schema, schema_name, review_ids, phase, label_config,
             max_output_tokens, prompt_version, extra=None):
        """Returns parsed JSON or None. Every attempt (success or failure) is written to calls.jsonl."""
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        est_in = (len(instructions) + len(payload)) // 2  # conservative chars->tokens
        reservation = call_cost(self.model, est_in, 0, max_output_tokens)
        self.ledger.reserve(reservation)
        base = {"role": role, "review_ids": list(review_ids), "model": self.model, "phase": phase,
                "label_config": label_config, "prompt_version": prompt_version, "reasoning_effort": self.effort,
                "run_id": self.run_id, **(extra or {})}
        settled = False
        try:
            for attempt in range(1, TRANSIENT_ATTEMPTS + 1):
                started = time.time()
                try:
                    resp = self.client.responses.create(
                        model=self.model, instructions=instructions, input=payload,
                        reasoning={"effort": self.effort}, max_output_tokens=max_output_tokens,
                        prompt_cache_key=label_config, store=False,
                        text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}})
                except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError) as e:
                    code = getattr(e, "code", None) or ""
                    status = getattr(e, "status_code", None)
                    self._log({**base, "request_id": f"local-{uuid.uuid4()}", "outcome": "failed", "attempt": attempt,
                               "error": f"{type(e).__name__}:{status}:{code}"[:200], "input_tokens": 0, "output_tokens": 0,
                               "usage_known": False, "cost_usd": 0.0, "latency_s": round(time.time() - started, 3),
                               "started_at": now()})
                    if code == "insufficient_quota" or "quota" in str(e).lower() or "spend limit" in str(e).lower():
                        raise BudgetStop("provider quota / project spend limit reached") from e
                    transient = isinstance(e, (RateLimitError, APITimeoutError, APIConnectionError)) or (status or 0) >= 500
                    if not transient or attempt == TRANSIENT_ATTEMPTS:
                        return None
                    retry_after = 0.0
                    try:
                        retry_after = float(e.response.headers.get("retry-after", 0))
                    except Exception:
                        pass
                    time.sleep(max(retry_after, min(30, 2 ** attempt)) + random.uniform(0, 1))
                    continue

                u = resp.usage
                cached = (u.input_tokens_details.cached_tokens or 0) if u.input_tokens_details else 0
                reasoning = (u.output_tokens_details.reasoning_tokens or 0) if u.output_tokens_details else 0
                cost = call_cost(self.model, u.input_tokens, cached, u.output_tokens)
                self.ledger.settle(reservation, cost)
                settled = True
                parsed, error = None, None
                if resp.status != "completed":
                    error = f"status_{resp.status}:{getattr(resp.incomplete_details, 'reason', '')}"
                    if "results" in schema.get("properties", {}):
                        items = salvage_results(resp.output_text or "")
                        if items:
                            parsed, error = {"results": items}, f"salvaged_{len(items)}_items_after_{error}"
                else:
                    refusal = any(getattr(c, "type", "") == "refusal" for o in resp.output for c in (getattr(o, "content", None) or []))
                    if refusal:
                        error = "refusal"
                    else:
                        try:
                            parsed = json.loads(resp.output_text)
                        except ValueError:
                            error = "unparseable_json"
                            if "results" in schema.get("properties", {}):
                                items = salvage_results(resp.output_text or "")
                                if items:
                                    parsed, error = {"results": items}, f"salvaged_{len(items)}_items_after_unparseable_json"
                if error:  # failures and salvages both keep the raw text for error analysis
                    raw = resp.output_text or ""
                    with self.log_lock, (self.calls_path.parent / "failed_outputs.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"request_id": resp.id, "error": error, "output_tokens": u.output_tokens,
                                            "head": raw[:1500], "tail": raw[-800:]}, ensure_ascii=False) + "\n")
                self._log({**base, "request_id": resp.id, "outcome": "succeeded" if parsed is not None else "failed",
                           "attempt": attempt, "error": error, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                           "cached_input_tokens": cached, "reasoning_tokens": reasoning, "usage_known": True,
                           "cost_usd": round(cost, 8), "latency_s": round(time.time() - started, 3), "started_at": now()})
                return parsed
            return None
        finally:
            if not settled:
                self.ledger.settle(reservation, 0.0)
