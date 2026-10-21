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
  "urgency_tier": "URGENT" | "Intermédiaire" | "Faible" | null,
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
  "other_notes": string | null,
  "recommended_tasks": [
    {
      "description": string,
      "suggested_trade": string | null,
      "urgency_tier": "URGENT" | "Intermédiaire" | "Faible" | null,
      "vendor_id": integer | null,
      "subcontractor_name": string | null,
      "notes": string | null
    }, ...
  ]
}

recommended_tasks = the schedulable work units for this call, each a single visit's worth of work for one trade. Verdict "single" requires at least one task. A problem spanning several trades (e.g. plumbing leak + damaged floor) → one task per trade, in the order the work should happen. "duplicate" → return an empty list (no tasks are created). "addition" → tasks only for the new, distinct work (they are proposed on the open call); empty list allowed. Also give at least one task for an "addition" forced to "single" by exclusive routing (A1/A2/A3/A3b/A4). Task description: short, plain, operational, in the output language. urgency_tier on a task is null unless it differs from the call's urgency_tier. vendor_id / subcontractor_name follow the same exclusive-vendor rules as the call-level fields — leave null unless the work is for that vendor. There is no assignee on a task: never name a person or initials; the dispatcher assigns. The same bans apply to task text (description, suggested_trade, notes): no financial content, no access codes, no routing codes.

There is NO assignee field. Do not include one. There is NO animals / pets field — do not include one; ignore any form yes/no pet answer. Never write employee initials (2–4 capital letters, e.g. CHGE) in title, problems, entry_permission, or other_notes. Vendor names (Duclos, Body Gym, Fortin, Éric) go in subcontractor_name only.
Same-unit open calls: same problem → verdict "duplicate" (flag only, title contains DOUBLON POTENTIEL). Different problem + routing A1/A2/A3/A3b/A4 → verdict "single" (own ticket, never addition). Different problem + normal routing (A0/A5) → verdict "addition" (system will merge into the open call).
urgency_tier is exactly "URGENT" (do today: active water including hidden leaks, backflow, no heat or hot water, person stuck, alarm/fire, lock not working, dead fridge, electrical or structural danger), "Intermédiaire" (priority, not necessarily today: contained slow leak, mould, non-critical appliance, any vermin, AC in a heatwave), "Faible" (non-urgent / can wait), or null when urgency cannot be judged. Do NOT put urgency codes in the title — title is a plain short summary only. Judge urgency from the problem content only — ignore any caller/form self-report of urgency (Gravity "Urgent ou non-urgent", intake urgent flag, or similar).
Routing codes (A0, A1, A2, A3, A3b, A4, A5) belong ONLY in the routing_rule field. NEVER write them in title, problems, entry_permission, other_notes, or any other text field — use plain operational language instead.
Access codes and combinations are FORBIDDEN in all text fields. When a keybox, door code, NIP, or combination appears in the source request, reference the device by label only (e.g. "keybox H", "clavier principal") — never include the digit sequence.
Exclusive vendors: A2 subcontractor_name is Body Gym. A3 (certain door/window replacement) is Duclos. A3b (unknown cause — diagnose first) leaves subcontractor_name null and must not name Duclos. A4 extermination names Éric. C4 plumbing names Fortin. Do not put those vendors on any other routing_rule.
When noting in other_notes why urgency was adjusted or how the work category informs routing, describe the work in plain operational terms (e.g. "intercom en partie commune", "employé affecté à l'immeuble") — never use a routing code as a category label.
When noting which geographic sector or territory an immeuble belongs to, or which dedicated worker covers it, use place names only (e.g. "Ste-Foy", "Rive-Sud", "secteur Châtelets", "Lévis-Ouest") — never use an internal designation as a geographic label in any text field.
When the user message lists required other_notes phrases (RÉQUÉRANT ABSENT, emménagement récent, bail anglais, LOGEMENT VACANT), other_notes must contain each phrase verbatim. Mention the lease language only when it is English.
heating_failure: true ONLY when the tenant reports no or insufficient heating of the dwelling itself (heating is a lessor obligation, art. 1864-1865 C.c.Q.). false when the heating mention is clearly something else (pool heater, thermostat stuck hot, summer-mode notice, routine maintenance). null when unclear — never guess.\
"""

_LANG_EN = """\
## Output language

The skill and guide above are in French — follow their rules exactly.
Write ALL human-readable JSON string fields in English: title, problems, entry_permission, other_notes, and recommended_tasks description / suggested_trade / notes.
Keep proper nouns and place names as-is (addresses, Ste-Foy, Duclos, etc.).
Enum / code fields stay exactly as specified (URGENT, Intermédiaire, Faible, C1–C4, A0–A5, YES/NO/CONDITIONAL, time buckets, etc.).
subcontractor_name: keep the vendor's real name; do not translate brand names.\
"""

_LANG_FR = """\
## Langue de sortie

Rédige TOUS les champs texte lisibles du JSON en français : title, problems, entry_permission, other_notes, ainsi que description / suggested_trade / notes de recommended_tasks.
Les codes / enums restent tels que spécifiés (URGENT, Intermédiaire, Faible, C1–C4, A0–A5, etc.).\
"""


def _load_documents() -> str:
    skill = (_DOCS_DIR / "SKILL.md").read_text(encoding="utf-8")
    guide = (_DOCS_DIR / "guide-coordonnateur-maintenance-v4_39.md").read_text(encoding="utf-8")
    return skill + "\n\n---\n\n" + guide


# Computed once at import; includes the output contract so any prompt change changes the hash.
DOCUMENTS_HASH: str = hashlib.sha256((_load_documents() + _OUTPUT_CONTRACT).encode()).hexdigest()


def build_system_prompt(*, lang: str = "fr") -> list[dict]:
    """
    Returns the system prompt as Anthropic content blocks for messages.create(system=...).

    Block 0 — skill + guide, cache_control='ephemeral': cached across calls.
    Block 1 — output contract, no cache_control: uncached, updated independently.
    Block 2 — output language (fr|en), uncached.
    """
    docs = _load_documents()
    lang_block = _LANG_EN if (lang or "fr").lower().startswith("en") else _LANG_FR
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
        {
            "type": "text",
            "text": lang_block,
        },
    ]


if __name__ == "__main__":
    blocks = build_system_prompt()
    total_chars = sum(len(b["text"]) for b in blocks)
    print(f"blocks:      {len(blocks)}")
    print(f"total chars: {total_chars:,}  (~{total_chars // 4:,} tokens)")
    print(f"cached block: {len(blocks[0]['text']):,} chars")
    print(f"DOCUMENTS_HASH: {DOCUMENTS_HASH}")
