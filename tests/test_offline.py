"""Offline tests (no API key, no network): validation, salvage, spend cap, bounded retries, resume, ranking.

    .venv/bin/python -m unittest tests/test_offline.py -v
"""

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx2  # noqa: E402  (the OpenAI SDK's HTTP layer)
import openai  # noqa: E402

from pipeline import enrich as enrich_mod  # noqa: E402
from pipeline import llm as llm_mod  # noqa: E402
from pipeline.io import FIELDS, read_jsonl  # noqa: E402
from pipeline.labels import fuzzy_span, validate  # noqa: E402
from pipeline.llm import BudgetStop, Ledger, salvage_results  # noqa: E402

GOOD = {"topic": "playback", "sub": "playback.stops_midway", "intent": "complaint", "severity": 3, "sentiment": -0.5,
        "needs_review": False, "entities": [], "quote": ""}


def _req():
    return httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _resp(status, headers=None):
    return httpx2.Response(status, request=_req(), headers=headers or {})


class Validation(unittest.TestCase):
    def test_short_review_quotes_itself(self):
        f, notes = validate(GOOD, "Songs stop after 10 seconds")
        self.assertEqual(f["evidence_quote"], "Songs stop after 10 seconds")

    def test_long_review_exact_quote(self):
        text = "x " * 70 + "the music keeps stopping halfway through every song" + " y" * 10
        f, _ = validate({**GOOD, "quote": "the music keeps stopping halfway"}, text)
        self.assertIn(f["evidence_quote"], text)

    def test_typo_corrected_quote_mapped_back_to_source(self):
        text = "a " * 70 + "evrthing is in premium membership only now"
        self.assertEqual(fuzzy_span("everything is in premium membership only", text), "evrthing is in premium membership only")

    def test_invented_quote_rejected_then_full_text_fallback_on_final_attempt(self):
        text = "b " * 70 + "app crashes"
        self.assertEqual(validate({**GOOD, "quote": "completely unrelated sentence here"}, text)[1], "quote_not_in_source")
        f, notes = validate({**GOOD, "quote": "completely unrelated sentence here"}, text, final_attempt=True)
        self.assertEqual(f["evidence_quote"], text.strip())
        self.assertTrue(f["needs_review"])

    def test_bad_enum_and_range_rejected(self):
        self.assertEqual(validate({**GOOD, "topic": "pricing"}, "x")[1], "invalid_topic")
        self.assertEqual(validate({**GOOD, "severity": 7}, "x")[1], "invalid_severity")
        self.assertEqual(validate({**GOOD, "sentiment": 1.5}, "x")[1], "invalid_sentiment")

    def test_unsupported_entities_dropped_and_praise_severity_forced_to_1(self):
        f, notes = validate({**GOOD, "intent": "praise", "severity": 3, "entities": ["shuffle", "Apple Music"]}, "I love shuffle")
        self.assertEqual(f["entities"], ["shuffle"])
        self.assertEqual(f["severity"], 1)

    def test_subtopic_must_match_topic(self):
        f, notes = validate({**GOOD, "sub": "billing.unwanted_charges"}, "x")
        self.assertEqual(f["subtopic"], "playback.general")


class Salvage(unittest.TestCase):
    def test_truncated_output_keeps_complete_items(self):
        self.assertEqual(len(salvage_results('{"results":[{"i":1},{"i":2},{"i":3,"top')), 2)

    def test_junk_after_json(self):
        self.assertEqual(len(salvage_results('{"results":[{"i":1}]} \n SD {"results":[{"i":9}]}')), 1)


class Spend(unittest.TestCase):
    def test_reservation_blocks_past_cap(self):
        with tempfile.TemporaryDirectory() as d:
            led = Ledger(0.01, Path(d) / "spend.json")
            led.reserve(0.006)
            with self.assertRaises(BudgetStop):
                led.reserve(0.006)
            led.settle(0.006, 0.002)
            led.reserve(0.006)  # room again after actual cost settles below the reservation


def fake_llm(client, d, cap=1.0):
    obj = llm_mod.LLM.__new__(llm_mod.LLM)
    obj.client, obj.model, obj.effort, obj.run_id = client, "gpt-6-luna", "none", "test"
    obj.ledger = Ledger(cap, Path(d) / "spend.json")
    obj.calls_path = Path(d) / "calls.jsonl"
    import threading
    obj.log_lock = threading.Lock()
    return obj


def ok_response(text, out_tokens=10):
    usage = SimpleNamespace(input_tokens=100, output_tokens=out_tokens, input_tokens_details=SimpleNamespace(cached_tokens=0),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=0))
    return SimpleNamespace(id="resp_test_%d" % id(text), status="completed", output=[], output_text=text, usage=usage,
                           incomplete_details=None)


CALL = dict(role="enrich", instructions="x", payload="y", schema={"properties": {"results": {}}}, schema_name="s",
            review_ids=["r1"], phase="initial", label_config="cfg", max_output_tokens=100, prompt_version="p")


@mock.patch.object(llm_mod.time, "sleep", lambda s: None)
class BoundedRetries(unittest.TestCase):
    def test_rate_limit_then_success_is_logged_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            client = mock.Mock()
            client.responses.create.side_effect = [
                openai.RateLimitError("slow down", response=_resp(429, {"retry-after": "0"}), body=None),
                ok_response('{"results":[]}')]
            out = fake_llm(client, d).call(**CALL)
            self.assertEqual(out, {"results": []})
            log = read_jsonl(Path(d) / "calls.jsonl")
            self.assertEqual([c["outcome"] for c in log], ["failed", "succeeded"])

    def test_persistent_outage_gives_up_after_4_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            client = mock.Mock()
            client.responses.create.side_effect = openai.APIConnectionError(request=_req())
            self.assertIsNone(fake_llm(client, d).call(**CALL))
            self.assertEqual(client.responses.create.call_count, llm_mod.TRANSIENT_ATTEMPTS)

    def test_quota_exhausted_stops_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            client = mock.Mock()
            client.responses.create.side_effect = openai.RateLimitError(
                "You exceeded your current quota", response=_resp(429), body={"code": "insufficient_quota"})
            with self.assertRaises(BudgetStop):
                fake_llm(client, d).call(**CALL)
            self.assertEqual(client.responses.create.call_count, 1)

    def test_local_cap_refuses_before_calling(self):
        with tempfile.TemporaryDirectory() as d:
            client = mock.Mock()
            with self.assertRaises(BudgetStop):
                fake_llm(client, d, cap=0.0).call(**CALL)
            client.responses.create.assert_not_called()


class FakeEnrichLLM:
    """Stands in for the model inside run_enrich: returns valid items, except item 2 is malformed on first sight."""
    seen = []

    def __init__(self, *a, **k):
        pass

    def call(self, *, review_ids, payload, **k):
        FakeEnrichLLM.seen.append(list(review_ids))
        items = json.loads(payload)["reviews"]
        res = []
        for it in items:
            bad = "MALFORMED" in it["t"] and len(FakeEnrichLLM.seen) == 1
            res.append({**GOOD, "i": it["i"], "topic": "pricing" if bad else "playback"})
        return {"results": res}


class EnrichFlow(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.csv = self.d / "in.csv"
        rows = [{"review_id": f"id{i}", "review_text": t, "review_rating": "1", "review_likes": "0", "app_version": "",
                 "review_timestamp": "2023-01-01 00:00:00"} for i, t in
                enumerate(["songs stop", "MALFORMED stops", "", "songs stop", "app crashes", "lag"])]
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        FakeEnrichLLM.seen = []

    def tearDown(self):
        shutil.rmtree(self.d)

    @mock.patch.object(enrich_mod, "LLM", FakeEnrichLLM)
    def test_retry_quarantine_cache_and_resume(self):
        run = self.d / "run"
        s = enrich_mod.run_enrich(self.csv, run, budget_usd=1.0, batch_size=2, max_batches=1, log=lambda *_: None)
        self.assertEqual(s["phase"], "initial")
        st = enrich_mod.State(run / "state.sqlite").all()
        self.assertEqual(st["id2"]["reason"], "empty_review_text")      # empty text quarantined explicitly
        self.assertEqual(st["id1"]["attempts"], 2)                      # malformed item retried exactly once
        self.assertEqual(st["id3"]["cache_source_id"], "id0")           # exact duplicate reuses its original
        before = set(enrich_mod.State(run / "state.sqlite").completed_ids())
        FakeEnrichLLM.seen = []
        s2 = enrich_mod.run_enrich(self.csv, run, budget_usd=1.0, batch_size=2, log=lambda *_: None)
        self.assertEqual(s2["phase"], "resume")
        sent = {rid for batch in FakeEnrichLLM.seen for rid in batch}
        self.assertFalse(sent & before, "resume must not resend completed IDs")
        self.assertEqual(len(enrich_mod.State(run / "state.sqlite").completed_ids()), 5)


class Ranking(unittest.TestCase):
    def test_rerank_is_byte_identical(self):
        run = ROOT / "runs" / "dev10k_v3"
        if not (run / "records.jsonl").exists():
            self.skipTest("dev10k_v3 not present")
        from pipeline.rank import build
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copy(run / "records.jsonl", tmp / "records.jsonl")
            build(tmp)
            first = (tmp / "ranking.csv").read_bytes(), (tmp / "membership.csv").read_bytes()
            build(tmp)
            self.assertEqual(first, ((tmp / "ranking.csv").read_bytes(), (tmp / "membership.csv").read_bytes()))
            self.assertEqual(first[0], (run / "ranking.csv").read_bytes())
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
