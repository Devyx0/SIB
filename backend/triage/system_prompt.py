"""
System prompt assembler for the AI triage service.

Cache structure: one cached block (skill + guide, ~75K tokens) + one
uncached block (output contract). Cache breakpoint sits between them so
the static documents are cached across calls while the contract can be
updated without invalidating the cache.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.core.config import settings

_DOCS_DIR: Path = settings.TRIAGE_PROMPT_DIR

_OUTPUT_CONTRACT = """\
## Output contract

Return ONLY valid JSON matching this schema. No prose, no explanation.

{
  "verdict": "single | duplicate | addition",
  "duplicate_of_request_id": null | integer,
  "addition_to_request_id": null | integer,
  "title": string,
  "problems": [string, ...],
  "entry_permission": string | null,
  "animals": string | null,
  "urgency_tier": "AJD" | null,
  "heating_failure": true | false | null,
  "complexity_tier": "C1" | "C2" | "C3" | "C4",
  "congestion_level": "N1" | "N2" | "N3" | "N4" | "N5",
  "time_estimate_bucket": "UNDER_30_MIN" | "MIN30_TO_1H" | "H1_TO_2H" | "H2_TO_4H" | "HALF_DAY_PLUS" | "TBD_ON_SITE",
  "delegable_status": "YES" | "NO" | "CONDITIONAL",
  "report_status": "CANNOT_WAIT" | "SUPERVISOR_DISCRETION" | "CAN_WAIT_SHORT_TERM" | "CAN_WAIT" | "NOT_APPLICABLE",
  "routing_rule": "A0" | "A1" | "A2" | "A3" | "A3b" | "A4" | "A5",
  "subcontractor_name": string | null,
  "vendor_id": integer | null,
  "synergy_request_ids": [integer, ...],
  "other_notes": string | null
}

There is NO assignee field. Do not include one.
Routing codes (A0, A1, A2, A3, A3b, A4, A5) belong ONLY in the routing_rule field. NEVER write them in title, problems, entry_permission, other_notes, or any other text field — use plain operational language instead.
Access codes and combinations are FORBIDDEN in all text fields. When a keybox, door code, NIP, or combination appears in the source request, reference the device by label only (e.g. "keybox H", "clavier principal") — never include the digit sequence.
When routing a door or window problem to a specialist for unknown-cause diagnosis, always name the specialist in subcontractor_name (e.g. Duclos for doors/windows). Never leave subcontractor_name null for this routing.
When noting in other_notes why urgency was adjusted or how the work category informs routing, describe the work in plain operational terms (e.g. "intercom en partie commune", "employé affecté à l'immeuble") — never use a routing code as a category label.
When noting which geographic sector or territory an immeuble belongs to, or which dedicated worker covers it, use place names only (e.g. "Ste-Foy", "Rive-Sud", "secteur Châtelets", "Lévis-Ouest") — never use an internal designation as a geographic label in any text field.
heating_failure: true ONLY when the tenant reports no or insufficient heating of the dwelling itself (heating is a lessor obligation, art. 1864-1865 C.c.Q.). false when the heating mention is clearly something else (pool heater, thermostat stuck hot, summer-mode notice, routine maintenance). null when unclear — never guess.\
"""


def _load_documents() -> str:
    skill = (_DOCS_DIR / "SKILL.md").read_text(encoding="utf-8")
    guide = (_DOCS_DIR / "guide-coordonnateur-maintenance-v4_39.md").read_text(encoding="utf-8")
    return skill + "\n\n---\n\n" + guide


# Computed once at import; includes the output contract so any prompt change changes the hash.
DOCUMENTS_HASH: str = hashlib.sha256((_load_documents() + _OUTPUT_CONTRACT).encode()).hexdigest()


def build_system_prompt() -> list[dict]:
    """
    Returns the system prompt as Anthropic content blocks for messages.create(system=...).

    Block 0 — skill + guide, cache_control='ephemeral': cached across calls.
    Block 1 — output contract, no cache_control: uncached, updated independently.
    """
    docs = _load_documents()
    return [
        {
            "type": "text",
            "text": docs,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": _OUTPUT_CONTRACT,
        },
    ]


if __name__ == "__main__":
    blocks = build_system_prompt()
    total_chars = sum(len(b["text"]) for b in blocks)
    print(f"blocks:      {len(blocks)}")
    print(f"total chars: {total_chars:,}  (~{total_chars // 4:,} tokens)")
    print(f"cached block: {len(blocks[0]['text']):,} chars")
    print(f"DOCUMENTS_HASH: {DOCUMENTS_HASH}")
