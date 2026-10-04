"""Common labels, the enrichment output schema, and code-side validation."""

import json
import math
import re
import unicodedata

from .io import INTENTS, ROOT, TOPICS

SCHEMA_VERSION = "schema_v2"  # v2 adds `sub` (frozen subtopic / issue ID)
TAXONOMY = json.loads((ROOT / "taxonomy" / "subtopics_v1.json").read_text(encoding="utf-8"))
ISSUE_IDS = [s["issue_id"] for subs in TAXONOMY["topics"].values() for s in subs]
INTENT_PRECEDENCE = ("cancellation", "complaint", "request", "praise", "unclear")
NO_PROBLEM_INTENTS = {"praise", "request", "unclear"}  # severity 1 by the shared definition
SHORT_TEXT_CHARS = 120  # at or below this, the whole (stripped) review is its own evidence quote
MAX_ENTITIES = 3


def item_schema(with_index=True):
    props = {
        "topic": {"type": "string", "enum": list(TOPICS)},
        "sub": {"type": "string", "enum": ISSUE_IDS},
        "intent": {"type": "string", "enum": list(INTENT_PRECEDENCE)},
        "severity": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "sentiment": {"type": "number"},
        "needs_review": {"type": "boolean"},
        "entities": {"type": "array", "items": {"type": "string"}},
        "quote": {"type": "string"},
    }
    if with_index:
        props = {"i": {"type": "integer"}, **props}
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


def batch_schema():
    return {"type": "object", "additionalProperties": False,
            "properties": {"results": {"type": "array", "items": item_schema()}}, "required": ["results"]}


_QUOTE_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "…": "."})


def _fold(ch):
    return unicodedata.normalize("NFKC", ch).translate(_QUOTE_FOLD).lower()


def find_span(quote, text):
    """Locate `quote` in `text` ignoring case, curly quotes and whitespace runs.
    Returns the exact original substring, or None. Never invents text."""
    norm, index = [], []
    prev_space = False
    for pos, ch in enumerate(text):
        if ch.isspace():
            if prev_space or not norm:
                continue
            norm.append(" ")
            index.append(pos)
            prev_space = True
        else:
            for c in _fold(ch):
                norm.append(c)
                index.append(pos)
            prev_space = False
    target = re.sub(r"\s+", " ", "".join(_fold(c) for c in quote)).strip()
    if not target:
        return None
    hay = "".join(norm)
    at = hay.find(target)
    if at < 0:
        return None
    start, end = index[at], index[at + len(target) - 1]
    return text[start:end + 1]


FUZZY_MIN_RATIO = 0.8
FALLBACK_MAX_CHARS = 600


def fuzzy_span(quote, text):
    """Closest word-aligned window of `text` to `quote` (handles the model silently fixing typos).
    Returns the exact original substring if similarity >= FUZZY_MIN_RATIO, else None."""
    from difflib import SequenceMatcher

    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    n = len(quote.split())
    if not words or not n:
        return None
    target = quote.lower()
    best, best_ratio = None, 0.0
    for size in range(max(1, n - 2), n + 3):
        for i in range(0, len(words) - size + 1):
            cand = text[words[i][0]:words[i + size - 1][1]]
            ratio = SequenceMatcher(None, cand.lower(), target, autojunk=False).ratio()
            if ratio > best_ratio:
                best, best_ratio = cand, ratio
    return best if best_ratio >= FUZZY_MIN_RATIO else None


def needs_quote(text):
    return len(text.strip()) > SHORT_TEXT_CHARS


def validate(item, text, final_attempt=False):
    """Validate one model item against its source text.
    Returns (fields, notes) on success or (None, error_reason) on failure.
    On the final attempt, a review of <= FALLBACK_MAX_CHARS whose quote still cannot be located
    uses its whole text as evidence (flagged needs_review) instead of being quarantined."""
    notes = []
    if item.get("topic") not in TOPICS:
        return None, "invalid_topic"
    if item.get("intent") not in INTENTS:
        return None, "invalid_intent"
    sev = item.get("severity")
    if type(sev) is not int or not 1 <= sev <= 5:
        return None, "invalid_severity"
    sent = item.get("sentiment")
    if type(sent) not in (int, float) or not math.isfinite(sent) or not -1 <= sent <= 1:
        return None, "invalid_sentiment"
    if type(item.get("needs_review")) is not bool:
        return None, "invalid_needs_review"
    ents = item.get("entities")
    if not isinstance(ents, list) or not all(isinstance(e, str) for e in ents):
        return None, "invalid_entities"

    # Evidence quote: short reviews quote themselves; long ones must match the source exactly.
    if not needs_quote(text):
        quote = text.strip()
    else:
        raw = (item.get("quote") or "").strip()
        if raw and raw in text:
            quote = raw
        elif not raw and len(text.strip()) <= FALLBACK_MAX_CHARS:
            quote = text.strip()  # model omitted the quote: the whole (<=600-char) review is its own evidence
            notes.append("quote_omitted_full_text")
        else:
            quote = find_span(raw, text) if raw else None
            if quote:
                notes.append("quote_span_repaired")
            elif raw and (quote := fuzzy_span(raw, text)):
                notes.append("quote_fuzzy_repaired")
            elif final_attempt and len(text.strip()) <= FALLBACK_MAX_CHARS:
                quote = text.strip()
                notes.append("quote_fallback_full_text")
            else:
                return None, "quote_not_in_source"

    # Entities must literally appear in the review; drop unsupported additions.
    lowered = text.lower()
    kept = []
    for e in ents:
        e = e.strip()
        if e and e.lower() in lowered and e.lower() not in (k.lower() for k in kept):
            kept.append(e)
    if len(kept) < len([e for e in ents if e.strip()]):
        notes.append("unsupported_entities_dropped")
    kept = kept[:MAX_ENTITIES]

    # Shared definition: praise, pure requests and unclear content carry severity 1.
    if item["intent"] in NO_PROBLEM_INTENTS and sev != 1:
        notes.append(f"severity_{sev}_set_to_1_for_{item['intent']}")
        sev = 1

    sub = item.get("sub")
    if not isinstance(sub, str) or sub not in ISSUE_IDS or not sub.startswith(item["topic"] + "."):
        notes.append(f"subtopic_mismatch:{sub}")
        sub = item["topic"] + ".general"

    fields = {"topic": item["topic"], "subtopic": sub, "intent": item["intent"], "sentiment": round(float(sent), 2),
              "severity": sev, "entities": kept, "evidence_quote": quote,
              "needs_review": bool(item["needs_review"] or any(n.startswith(("severity_", "quote_fallback")) for n in notes))}
    return fields, notes
