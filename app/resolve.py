"""Entity resolution for BharatWatch data ingestion.

Match priority: PAN > DIN > CIN > exact normalized name > fuzzy name.
Fuzzy matches in the grey zone go to the manual review queue.

If the `anthropic` SDK is installed and ANTHROPIC_API_KEY is set, grey-zone
matches are additionally adjudicated by Claude (claude-opus-4-8); otherwise
they stay in the review queue for a human.
"""
import json
import os
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db

HONORIFICS = re.compile(
    r"^(shri|smt|dr|kum|sri|thiru|md|mr|mrs|ms|adv|prof)\.?\s+", re.I
)
AUTO_ACCEPT = 0.92
REVIEW_FLOOR = 0.75


def normalize_name(name):
    if not name:
        return ""
    n = name.strip()
    n = HONORIFICS.sub("", n)
    n = re.sub(r"\b(pvt|private)\b\.?", "pvt", n, flags=re.I)
    n = re.sub(r"\b(ltd|limited)\b\.?", "ltd", n, flags=re.I)
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n)
    return n.upper().strip()


def fuzzy(a, b):
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def find_entity(row, etype=None):
    """Return (entity_id, confidence, method) or (None, best_conf, 'none')."""
    c = get_db().cursor()
    for key in ("pan", "din", "cin"):
        v = (row.get(key) or "").strip().upper()
        if v:
            hit = c.execute(f"SELECT id FROM entities WHERE UPPER({key})=?", (v,)).fetchone()
            if hit:
                return hit["id"], 1.0, key.upper()
    name = row.get("name", "")
    if not name:
        return None, 0.0, "none"
    norm = normalize_name(name)
    if etype:
        cands = c.execute("SELECT id, name, state FROM entities WHERE type=?", (etype,)).fetchall()
    else:
        cands = c.execute("SELECT id, name, state FROM entities").fetchall()
    best, best_conf = None, 0.0
    for cand in cands:
        conf = fuzzy(name, cand["name"])
        # constituency/state agreement nudges confidence
        if conf > 0.5 and row.get("state") and cand["state"]:
            conf += 0.04 if row["state"].strip().lower() == cand["state"].strip().lower() else -0.04
        if normalize_name(cand["name"]) == norm:
            conf = max(conf, 0.99)
        if conf > best_conf:
            best, best_conf = cand["id"], conf
    if best and best_conf >= AUTO_ACCEPT:
        return best, best_conf, "fuzzy"
    return (best, best_conf, "grey") if best and best_conf >= REVIEW_FLOOR else (None, best_conf, "none")


def ai_adjudicate(row, candidate_name):
    """Optional Claude adjudication of a grey-zone match. Returns True/False/None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=512,
            thinking={"type": "adaptive"},
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "same_entity": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["same_entity", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            messages=[{
                "role": "user",
                "content": (
                    "You are resolving Indian public-records entities. Are these the same "
                    "person/company? Consider honorifics, transliteration variants, and "
                    "Pvt Ltd abbreviations.\n"
                    f"Incoming record: {json.dumps(row, ensure_ascii=False)}\n"
                    f"Existing entity name: {candidate_name}"
                ),
            }],
        )
        text = next(b.text for b in response.content if b.type == "text")
        return bool(json.loads(text)["same_entity"])
    except Exception:
        return None
