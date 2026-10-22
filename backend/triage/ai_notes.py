"""Normalize triage AI notes into ai_important_notes / ai_next_steps arrays."""
from __future__ import annotations

import re

_HEADER = [
    ("summary", re.compile(r"^(#{1,3}\s*)?(summary|résumé)\s*:?\s*$", re.I)),
    ("important", re.compile(
        r"^(#{1,3}\s*)?(important(\s+notes?)?|notes?\s+importantes?)\s*:?\s*$", re.I,
    )),
    ("next", re.compile(
        r"^(#{1,3}\s*)?(next(\s+steps?)?|prochaines?\s+étapes?)\s*:?\s*$", re.I,
    )),
]


def _clean_list(raw) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    out = [str(x).strip() for x in raw if x is not None and str(x).strip()]
    return out or None


def parse_other_notes(text: str | None) -> tuple[list[str] | None, list[str] | None]:
    """Split legacy/structured other_notes into (important, next)."""
    raw = (text or "").strip()
    if not raw:
        return None, None
    lines = raw.splitlines()
    buckets: dict[str, list[str]] = {"summary": [], "important": [], "next": []}
    current: str | None = None
    saw = False
    orphan: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        hdr = next((k for k, re_h in _HEADER if re_h.match(s)), None)
        if hdr:
            current, saw = hdr, True
            continue
        cleaned = re.sub(r"^[-*•]\s+", "", s).strip()
        if not cleaned:
            continue
        if current:
            buckets[current].append(cleaned)
        else:
            orphan.append(cleaned)
    if not saw:
        return orphan or None, None
    important = buckets["important"] + orphan
    return (important or None), (buckets["next"] or None)


def normalize_parsed(parsed: dict) -> None:
    """Ensure ai_important_notes / ai_next_steps on the parsed triage dict.

    Prefers explicit array fields from the model; falls back to parsing other_notes.
    Mutates parsed in place. Keeps other_notes as a joined blob for gates/legacy.
    """
    important = _clean_list(parsed.get("ai_important_notes"))
    next_steps = _clean_list(parsed.get("ai_next_steps"))
    # Alternate key the model might use
    if important is None:
        important = _clean_list(parsed.get("important_notes"))
    if important is None or next_steps is None:
        p_imp, p_next = parse_other_notes(parsed.get("other_notes") if isinstance(parsed.get("other_notes"), str) else None)
        if important is None:
            important = p_imp
        if next_steps is None:
            next_steps = p_next

    parsed["ai_important_notes"] = important
    parsed["ai_next_steps"] = next_steps

    # Prefill Call notes next_steps from AI bullets (plain lines).
    if next_steps:
        parsed["next_steps"] = "\n".join(next_steps)
    elif "next_steps" not in parsed:
        parsed["next_steps"] = None

    reasoning = parsed.get("reasoning")
    if reasoning is None:
        reasoning = parsed.get("ai_reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        parsed["ai_reasoning"] = reasoning.strip()
        parsed["reasoning"] = parsed["ai_reasoning"]
    else:
        parsed["ai_reasoning"] = None
        parsed["reasoning"] = None

    # Keep other_notes as a searchable blob (rentroll phrases, financial gates).
    blob_parts: list[str] = []
    if important:
        blob_parts.extend(important)
    if next_steps:
        blob_parts.extend(next_steps)
    if blob_parts:
        parsed["other_notes"] = "\n".join(blob_parts)
    elif not isinstance(parsed.get("other_notes"), str) or not parsed["other_notes"].strip():
        parsed["other_notes"] = None


def append_important(parsed: dict, note: str) -> None:
    """Append one Important bullet (e.g. weather escalation)."""
    note = note.strip()
    if not note:
        return
    normalize_parsed(parsed)
    notes = list(parsed.get("ai_important_notes") or [])
    notes.append(note)
    parsed["ai_important_notes"] = notes
    blob = parsed.get("other_notes")
    parsed["other_notes"] = f"{blob}\n{note}" if blob else note
