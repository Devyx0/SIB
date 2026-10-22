"""Normalize the triage `title` field to an issue-only one-liner."""
from __future__ import annotations

import re

# Calendar-style titles: "[AJD] 1035-308 Pie XII: issue" — drop the location head.
_URGENCY_PREFIX = re.compile(r"^(?:AJD|ajd)\s+")
_EN_TRAITEMENT = re.compile(r"^\[EN\s+TRAITEMENT\]\s+", re.IGNORECASE)
_LOC_COLON = re.compile(r"^(.+?)\s*:\s*(.+)$")
# Unit-ish: "1035-308", "3140-501", or a head that starts with a civic number.
_UNITISH = re.compile(r"\d+-\d+|\A\d")


def clean_issue_title(title: str | None) -> str | None:
    """Keep the issue text only — no urgency code, no unit/address prefix.

    Location already lives on the request (building / unit fields). Returns the
    original string unchanged when it does not look like a calendar title.
    """
    if not isinstance(title, str):
        return title
    t = title.strip()
    if not t:
        return title
    t = _EN_TRAITEMENT.sub("", t)
    t = _URGENCY_PREFIX.sub("", t).strip()
    m = _LOC_COLON.match(t)
    if m:
        head, body = m.group(1).strip(), m.group(2).strip()
        if body and _UNITISH.search(head):
            t = body
    return t.strip() or title.strip()


def apply_clean_title(parsed: dict) -> None:
    """Mutate parsed['title'] in place."""
    if "title" in parsed:
        parsed["title"] = clean_issue_title(parsed.get("title"))
