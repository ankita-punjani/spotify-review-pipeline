"""Stage 4a — Issue-taxonomy discovery (group role, development data only).

A model proposes subtopics per topic from a bounded random sample of development complaints.
A person reviews the proposal and freezes it as taxonomy/subtopics_v1.json; enrichment then tags
each complaint with one frozen subtopic, so final issue membership is assigned without a second pass.
"""

import hashlib
import json
from pathlib import Path

from .enrich import State
from .io import ROOT, TOPICS, write_json
from .llm import LLM, Ledger

PROMPT_VERSION = "discover_v1"
MODEL, EFFORT = "gpt-6-luna", "low"
SAMPLE_PER_TOPIC = 120
SEED = "discover-v1"

TOPIC_DEFS = {
    "access": "Login, signup, password or account access",
    "usability": "Navigation, controls, layout, queue/playlist management, ad interruptions",
    "playback": "Playback failure, crashes, lag, connection failures, audio quality, resource use",
    "downloads": "Downloading, saved music, offline listening, disappearing downloads",
    "catalog": "Missing songs/artists, search/discovery, recommendations, lyrics availability",
    "billing": "Price, charges, subscriptions, paywalls, premium entitlement; explicitly premium-only controls",
    "support": "Contacting support and the support response",
    "other": "General criticism, unrelated content, or no supported specific topic",
}


def schema():
    sub = {"type": "object", "additionalProperties": False,
           "properties": {"code": {"type": "string"}, "name": {"type": "string"}, "definition": {"type": "string"},
                          "example_ids": {"type": "array", "items": {"type": "string"}},
                          "share_estimate": {"type": "number"}},
           "required": ["code", "name", "definition", "example_ids", "share_estimate"]}
    return {"type": "object", "additionalProperties": False,
            "properties": {"subtopics": {"type": "array", "items": sub}}, "required": ["subtopics"]}


def run_discover(dev_run, out_dir, budget_usd):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = State(Path(dev_run) / "state.sqlite").all()
    instructions = (ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    llm = LLM(MODEL, EFFORT, Ledger(budget_usd, out_dir / "spend.json"), out_dir / "calls.jsonl", out_dir.name)
    proposal = {"prompt_version": PROMPT_VERSION, "model": MODEL, "effort": EFFORT, "source_run": str(dev_run),
                "sample_per_topic": SAMPLE_PER_TOPIC, "seed": SEED, "topics": {}}
    for topic in TOPICS:
        pool = []
        for rid, r in recs.items():
            if r["status"] != "completed" or r["cache_source_id"]:
                continue
            f = json.loads(r["fields"])
            if f["topic"] == topic and f["intent"] in ("complaint", "cancellation"):
                pool.append((hashlib.sha256(f"{SEED}:{rid}".encode()).hexdigest(), rid, f["evidence_quote"][:240]))
        sample = sorted(pool)[:SAMPLE_PER_TOPIC]
        if not sample:
            continue
        payload = json.dumps({"topic": topic, "definition": TOPIC_DEFS[topic],
                              "complaints": [{"id": rid, "quote": q} for _, rid, q in sample]}, ensure_ascii=False)
        out = llm.call(role="group", instructions=instructions, payload=payload, schema=schema(),
                       schema_name="taxonomy", review_ids=[rid for _, rid, _ in sample], phase="initial",
                       label_config=f"{MODEL}+{PROMPT_VERSION}+effort-{EFFORT}", max_output_tokens=3000,
                       prompt_version=PROMPT_VERSION, extra={"stage": "discover", "topic": topic})
        ids = {rid for _, rid, _ in sample}
        if out:
            for s in out["subtopics"]:
                s["example_ids"] = [x for x in s["example_ids"] if x in ids]  # reject invented IDs
        proposal["topics"][topic] = {"pool_size": len(pool), "sample_size": len(sample),
                                     "subtopics": out["subtopics"] if out else None}
        print(f"[discover] {topic}: pool {len(pool)}, sample {len(sample)} -> "
              f"{[s['code'] for s in out['subtopics']] if out else 'FAILED'}")
    write_json(out_dir / "proposal.json", proposal)
    return proposal
