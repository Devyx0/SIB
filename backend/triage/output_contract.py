"""
Output contract parser and validation gates for the AI triage service.

Gates run in order; first failure wins. A response that violated a gate is
not sanitised — it is rejected entirely and the caller decides on retry.
"""
from __future__ import annotations

import json
import re

from backend.domain.urgency import URGENCY_VALUES as _URGENCY_STORED


class ValidationError(Exception):
    pass


# Exclusive / auto-routed categories — never merge into an open same-unit call
# (an `addition` with one of these is rewritten to `single` by the service).
EXCLUSIVE_ROUTING = frozenset({"A1", "A2", "A3", "A3b", "A4"})


OUTPUT_SCHEMA = {
    "verdict": "single | duplicate | addition",
    "duplicate_of_request_id": "int | null",
    "addition_to_request_id": "int | null",
    "title": "str",
    "problems": "list[str]",
    "entry_permission": "str | null",
    "urgency_tier": "URGENT | Intermédiaire | Faible | null",
    "heating_failure": "bool | null",
    "complexity_tier": "C1|C2|C3|C4",
    "congestion_level": "N1|N2|N3|N4|N5",
    "time_estimate_bucket": "UNDER_30_MIN|MIN30_TO_1H|H1_TO_2H|H2_TO_4H|HALF_DAY_PLUS|TBD_ON_SITE",
    "delegable_status": "YES|NO|CONDITIONAL",
    "report_status": "CANNOT_WAIT|SUPERVISOR_DISCRETION|CAN_WAIT_SHORT_TERM|CAN_WAIT|NOT_APPLICABLE",
    "routing_rule": "A0|A1|A2|A3|A3b|A4|A5",
    "subcontractor_name": "str | null",
    "vendor_id": "int | null",
    "synergy_request_ids": "list[int]",
    "ai_important_notes": "list[str] | null",
    "ai_next_steps": "list[str] | null",
    "reasoning": "str | null",
    "other_notes": "str | null",  # legacy; prefer the two arrays
    "recommended_tasks": (
        "list[{description: str, suggested_trade?: str, urgency_tier?: URGENT|Intermédiaire|Faible|null, "
        "vendor_id?: int|null, subcontractor_name?: str|null, notes?: str|null}] "
        "— ≥1 required when verdict is single"
    ),
}

_FINANCIAL_TERMS = re.compile(
    r"\b(loyer|arr[eé]rages|arri[eé]r[eé]|solde|caution|arrears|deposit|guarantor|endosseur)\b",
    re.IGNORECASE,
)
_CURRENCY_AMOUNT = re.compile(r"\d[\d\s,]*\$|[$€£]\d")
# dépôt is ambiguous (key handover vs financial deposit); only fire when a financial-context
# word or currency amount appears within this many chars on either side.
_DEPOT_TERM = re.compile(r"(?<![Hh][Oo][Mm][Ee] )\bd[eé]p[oô]t\b", re.IGNORECASE)
_DEPOT_FINANCIAL_CTX = re.compile(
    r"\d[\d\s,]*\$|[$€£]\d|\b(montant|remboursement|virement)\b",
    re.IGNORECASE,
)
_DEPOT_WINDOW = 60

# Access-code gate: a 4–8 digit sequence only fires when an access-context term
# appears within _CODE_WINDOW chars on either side.  Bare numbers (building
# addresses, years, request IDs) have no access-context term nearby.
_ACCESS_CONTEXT = re.compile(
    r"\b(code|clavier|NIP|combinaison|cadenas|keybox|lockbox|serrure|digicode)\b"
    r"|bo[iî]te\s+[aà]\s+cl[eé]|boite\s+a\s+cle",
    re.IGNORECASE,
)
_DIGIT_SEQ = re.compile(r"\b\d{4,8}\b")
_YEAR_LIKE  = re.compile(r"\b(19|20)\d{2}\b")   # years are never access codes
_ADDR_SUFFIX = re.compile(r"-\d{1,4}\b")         # civic address suffix like 3485-103
_ADDR_PREPOSITION = re.compile(r"\b(du|au|de)\s+$", re.IGNORECASE)  # "du 3094 Châtelets"
_CODE_WINDOW = 40
_INTERNAL_VOCAB = re.compile(
    r"\bA[0-5]b?\b|r[eè]gle\s+\d+|\bskill\b|guide\s+v\d|section\s+coordos|follow-up\s+terrain",
    re.IGNORECASE,
)
# "stationnement A5", "borne A5" — physical parking bay labels, not routing codes
_PARKING_BAY = re.compile(r"\b(stationnement|borne|espace)\s+$", re.IGNORECASE)
# "voir fiche Chamonix 1175" — model citing a technical sheet by building number
_FICHE_REF = re.compile(r"\bfiche\b", re.IGNORECASE)

# Urgency is a plain field — no calendar title prefix required anymore.
_URGENCY_VALUES = frozenset({None}) | _URGENCY_STORED
_INITIALS = re.compile(r"\b[A-Z]{2,4}\b")
# Operational tokens that are not employee initials.
_INITIALS_OK = frozenset({
    "URGENT", "ASNU", "SDB", "WC", "AC", "BBQ", "LED", "PVC", "TAL", "CVAC",
    "NB", "OK", "GFCI", "AMP", "USB", "TV", "HD", "NIP",
    # Roman numerals / street tokens that appear in Québec addresses
    "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "XIII",
})


_PEST_TEXT = re.compile(
    r"extermin|coquerelle|punais|fourmi|gu[eê]pe|vermine|souris|rat\b",
    re.IGNORECASE,
)
_PLUMBING_TEXT = re.compile(r"plomberie|plombier|colonne d'eau|refoulement", re.IGNORECASE)


_VENDOR_RULE = {"body_gym": "A2", "duclos": "A3", "eric": "A4"}  # exclusive vendor → its only routing rule


def _vendor_kind(name: str) -> str | None:
    n = name or ""
    if not n.strip():
        return None
    if re.search(r"body\s*gym", n, re.IGNORECASE):
        return "body_gym"
    if re.search(r"duclos", n, re.IGNORECASE):
        return "duclos"
    if re.search(r"[eé]ric", n, re.IGNORECASE):
        return "eric"
    if re.search(r"fortin", n, re.IGNORECASE):
        return "fortin"
    return "other"


_TASK_TEXT_KEYS = ("description", "suggested_trade", "notes")


def _recommended_tasks(parsed: dict) -> list:
    """The raw recommended_tasks value as a list (anything else counts as none)."""
    tasks = parsed.get("recommended_tasks")
    return tasks if isinstance(tasks, list) else []


def _check_recommended_tasks(parsed: dict) -> str | None:
    """Shape check; returns a rejection detail or None. Absent/null is legal here
    (only `single` requires tasks — gate 7)."""
    raw = parsed.get("recommended_tasks")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return "recommended_tasks must be a list"
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            return f"recommended_tasks[{i}] must be an object"
        desc = t.get("description")
        if not isinstance(desc, str) or not desc.strip():
            return f"recommended_tasks[{i}].description is required"
        for key in ("suggested_trade", "subcontractor_name", "notes"):
            v = t.get(key)
            if v is not None and not isinstance(v, str):
                return f"recommended_tasks[{i}].{key} must be a string or null"
        vid = t.get("vendor_id")
        if vid is not None and (not isinstance(vid, int) or isinstance(vid, bool)):
            return f"recommended_tasks[{i}].vendor_id must be an integer or null"
    return None


def _text_fields(parsed: dict) -> list[str]:
    out = []
    for key in ("title", "entry_permission", "other_notes", "reasoning", "ai_reasoning"):
        v = parsed.get(key)
        if isinstance(v, str):
            out.append(v)
    for key in ("ai_important_notes", "ai_next_steps", "problems"):
        for p in parsed.get(key) or []:
            if isinstance(p, str):
                out.append(p)
    for t in _recommended_tasks(parsed):
        if isinstance(t, dict):
            out.extend(t[k] for k in _TASK_TEXT_KEYS if isinstance(t.get(k), str))
    return out


def _notes_blob(parsed: dict) -> str:
    """Joined text used by rentroll phrase checks."""
    parts: list[str] = []
    if isinstance(parsed.get("other_notes"), str):
        parts.append(parsed["other_notes"])
    for key in ("ai_important_notes", "ai_next_steps"):
        for p in parsed.get(key) or []:
            if isinstance(p, str):
                parts.append(p)
    return "\n".join(parts)


def parse_response(raw: str) -> dict:
    """Parse model's raw text as JSON; strips markdown fences. Raises ValidationError on failure."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON parse failed: {exc}") from exc


def validate(
    parsed: dict,
    conn,
    request_id: int,
    *,
    expected_congestion: str | None = None,
    required_notes: list[str] | None = None,
) -> tuple[str, str | None]:
    """
    Run all gates in order. Returns (result, detail).
    result: 'accepted' | 'rejected_<gate>' | 'error'
    detail: None on accept, rejection reason otherwise.
    """
    # Gate 1 — no assignee field (rule 20/37)
    if any("assign" in k.lower() for k in parsed):
        return "rejected_no_assignee_field", "Response contains an assignee field"
    for t in _recommended_tasks(parsed):
        if isinstance(t, dict) and any("assign" in k.lower() for k in t):
            return "rejected_no_assignee_field", "recommended_tasks entry contains an assignee field"

    urgency = parsed.get("urgency_tier")
    if urgency not in _URGENCY_VALUES:
        return (
            "rejected_invalid_urgency",
            f"urgency_tier must be URGENT, Intermédiaire, Faible, or null, got {urgency!r}",
        )

    bad_tasks = _check_recommended_tasks(parsed)
    if bad_tasks:
        return "rejected_invalid_recommended_tasks", bad_tasks
    for i, t in enumerate(_recommended_tasks(parsed)):
        t_urgency = t.get("urgency_tier")
        if t_urgency not in _URGENCY_VALUES:
            return (
                "rejected_invalid_urgency",
                f"recommended_tasks[{i}].urgency_tier must be URGENT, Intermédiaire, Faible, or null, got {t_urgency!r}",
            )

    text_fields = _text_fields(parsed)

    # Gate 2 — no currency amounts in problems (rule 9)
    for p in parsed.get("problems", []):
        if isinstance(p, str) and _CURRENCY_AMOUNT.search(p):
            return "rejected_financial_content_problems", f"Currency amount in problems: {p!r}"

    # Gate 3 — no financial terms in any text field (rule 10)
    for t in text_fields:
        m = _FINANCIAL_TERMS.search(t)
        if m:
            return "rejected_financial_content", f"Financial term {m.group()!r} in text"
        for dm in _DEPOT_TERM.finditer(t):
            s = max(0, dm.start() - _DEPOT_WINDOW)
            e = min(len(t), dm.end() + _DEPOT_WINDOW)
            if _DEPOT_FINANCIAL_CTX.search(t[s:e]):
                return "rejected_financial_content", "Financial deposit context in text"

    # Gate 4 — no access-code digit near an access-context term (rule 11)
    for t in text_fields:
        for digit_m in _DIGIT_SEQ.finditer(t):
            if _YEAR_LIKE.fullmatch(digit_m.group()):
                continue  # years are not codes
            if _ADDR_SUFFIX.match(t, digit_m.end()):
                continue  # civic address like 3485-103, not a code
            if digit_m.start() > 0 and t[digit_m.start() - 1] == "#":
                continue  # request reference like #7722, not a code
            pre = t[max(0, digit_m.start() - 4):digit_m.start()]
            if _ADDR_PREPOSITION.search(pre):
                continue  # building address after French preposition (e.g. "du 3094 Châtelets")
            s = max(0, digit_m.start() - _CODE_WINDOW)
            e = min(len(t), digit_m.end() + _CODE_WINDOW)
            if _FICHE_REF.search(t[s:e]):
                continue  # building address cited in a technical-sheet cross-reference
            if _ACCESS_CONTEXT.search(t[s:e]):
                return "rejected_access_code_content", f"Digit {digit_m.group()!r} near access-context term"

    # Gate 5 — no internal vocabulary (rule 7)
    for t in text_fields:
        for m in _INTERNAL_VOCAB.finditer(t):
            tok = m.group()
            if re.fullmatch(r"A[0-5]b?", tok, re.IGNORECASE):
                pre = t[max(0, m.start() - 20):m.start()]
                if _PARKING_BAY.search(pre):
                    continue  # physical parking bay label (e.g. "stationnement A5")
            return "rejected_internal_vocabulary", f"Internal vocabulary {tok!r} in text"

    # Gate 5b — no employee initials in prose (rule 37)
    for t in text_fields:
        for m in _INITIALS.finditer(t):
            if m.group() not in _INITIALS_OK:
                return "rejected_assignee_initials", f"Employee-style initials {m.group()!r} in text"

    # Gate 6 — exclusive vendors match the routing rule (skill §10)
    routing = parsed.get("routing_rule", "")
    sub = parsed.get("subcontractor_name") or ""
    kind = _vendor_kind(sub)
    blob = " ".join(text_fields)
    if routing == "A2" and kind != "body_gym":
        return "rejected_routing_inconsistent", f"A2 requires Body Gym, got {sub!r}"
    if routing == "A3" and kind != "duclos":
        return "rejected_routing_inconsistent", f"A3 (certain replacement) requires Duclos, got {sub!r}"
    if routing == "A3b" and kind is not None:
        return "rejected_routing_inconsistent", f"A3b diagnoses first — no subcontractor, got {sub!r}"
    if routing == "A4" and _PEST_TEXT.search(blob) and kind != "eric":
        return "rejected_routing_inconsistent", f"A4 extermination requires Éric, got {sub!r}"
    if (
        parsed.get("complexity_tier") == "C4"
        and _PLUMBING_TEXT.search(blob)
        and kind != "fortin"
    ):
        return "rejected_routing_inconsistent", f"C4 plumbing requires Fortin, got {sub!r}"
    if kind == "body_gym" and routing != "A2":
        return "rejected_routing_inconsistent", f"Body Gym is A2 only, got {routing}"
    if kind == "duclos" and routing != "A3":
        return "rejected_routing_inconsistent", f"Duclos is A3 only, got {routing}"
    if kind == "eric" and routing != "A4":
        return "rejected_routing_inconsistent", f"Éric is A4 only, got {routing}"
    if routing == "A1" and kind is not None:
        return "rejected_routing_inconsistent", f"A1 expects no subcontractor, got {sub!r}"
    # Task-level vendors obey the same exclusive-vendor rules as the call-level one.
    for i, t in enumerate(_recommended_tasks(parsed)):
        t_sub = t.get("subcontractor_name")
        t_kind = _vendor_kind(t_sub or "")
        if t_kind is None:
            continue
        if routing == "A1" or (t_kind in _VENDOR_RULE and routing != _VENDOR_RULE[t_kind]):
            return (
                "rejected_routing_inconsistent",
                f"recommended_tasks[{i}] vendor {t_sub!r} does not fit routing {routing}",
            )

    if expected_congestion and parsed.get("congestion_level") != expected_congestion:
        return (
            "rejected_congestion",
            f"congestion_level must be {expected_congestion}, got {parsed.get('congestion_level')!r}",
        )

    if required_notes:
        notes = _notes_blob(parsed)
        missing = [p for p in required_notes if p not in notes]
        if missing:
            return "rejected_rentroll", f"ai notes missing {missing!r}"

    # Gate 7 — duplicate / addition must cite an open same-unit call (rule 12)
    verdict = parsed.get("verdict")
    if verdict == "single":
        if parsed.get("duplicate_of_request_id") is not None or parsed.get("addition_to_request_id") is not None:
            return "rejected_invalid_verdict_refs", "single verdict must not set duplicate/addition refs"
        if not _recommended_tasks(parsed):
            return "rejected_missing_recommended_tasks", "single verdict requires at least one recommended task"
    elif verdict == "duplicate":
        ref_id = parsed.get("duplicate_of_request_id")
        if not isinstance(ref_id, int):
            return "rejected_invalid_duplicate_ref", "duplicate_of_request_id missing or not an integer"
        if ref_id == request_id:
            return "rejected_invalid_duplicate_ref", "duplicate_of_request_id references the request itself"
        title = parsed.get("title") or ""
        if not re.search(r"DOUBLON\s+POTENTIEL", title, re.IGNORECASE):
            return "rejected_missing_doublon_mark", "duplicate title must contain DOUBLON POTENTIEL"
        if conn is not None:
            ok, detail = _check_dup_add_ref(
                conn, request_id, ref_id, expect_same_problem=True, parsed=parsed,
            )
            if not ok:
                return "rejected_invalid_duplicate_ref", detail
    elif verdict == "addition":
        # Exclusive routing → the service rewrites this to `single`, so it needs tasks too.
        if routing in EXCLUSIVE_ROUTING and not _recommended_tasks(parsed):
            return (
                "rejected_missing_recommended_tasks",
                "addition with exclusive routing becomes a single call and requires at least one recommended task",
            )
        ref_id = parsed.get("addition_to_request_id")
        if not isinstance(ref_id, int):
            return "rejected_invalid_addition_ref", "addition_to_request_id missing or not an integer"
        if ref_id == request_id:
            return "rejected_invalid_addition_ref", "addition_to_request_id references the request itself"
        if conn is not None:
            ok, detail = _check_dup_add_ref(
                conn, request_id, ref_id, expect_same_problem=False, parsed=parsed,
            )
            if not ok:
                return "rejected_invalid_addition_ref", detail
    else:
        return "rejected_invalid_verdict", f"verdict must be single|duplicate|addition, got {verdict!r}"

    # Gate 7b — task vendor_ids must exist (a bad FK would abort the write path)
    if conn is not None:
        vendor_ids = [
            t["vendor_id"] for t in _recommended_tasks(parsed) if t.get("vendor_id") is not None
        ]
        if vendor_ids:
            ok, detail = _check_vendors_exist(conn, vendor_ids)
            if not ok:
                return "rejected_invalid_recommended_tasks", detail

    # Gate 8 — synergy / peer refs must not cite §4.2 mechanically excluded titles
    if conn is not None:
        cite_ids: list[int] = []
        for sid in parsed.get("synergy_request_ids") or []:
            if isinstance(sid, int):
                cite_ids.append(sid)
        for key in ("duplicate_of_request_id", "addition_to_request_id"):
            rid = parsed.get(key)
            if isinstance(rid, int):
                cite_ids.append(rid)
        if cite_ids:
            ok, detail = _check_not_mechanically_excluded(conn, cite_ids)
            if not ok:
                return "rejected_excluded_candidate", detail

    return "accepted", None


def _check_vendors_exist(conn, vendor_ids: list[int]) -> tuple[bool, str | None]:
    uniq = list(dict.fromkeys(vendor_ids))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vendor_id FROM vendor_contact WHERE vendor_id = ANY(%s)", (uniq,),
            )
            rows = cur.fetchall()
    except Exception as exc:
        return False, f"DB lookup failed: {exc}"
    found = {(r["vendor_id"] if isinstance(r, dict) else r[0]) for r in rows}
    missing = [v for v in uniq if v not in found]
    if missing:
        return False, f"recommended_tasks vendor_id {missing!r} not found"
    return True, None


def _check_not_mechanically_excluded(conn, request_ids: list[int]) -> tuple[bool, str | None]:
    """Reject when any cited request_id has a §4.2-excluded raw_title."""
    from .context_builder import is_mechanically_excluded

    uniq = list(dict.fromkeys(request_ids))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT request_id, raw_title
                FROM maintenance_request
                WHERE request_id = ANY(%s)
                """,
                (uniq,),
            )
            rows = cur.fetchall()
    except Exception as exc:
        return False, f"DB lookup failed: {exc}"

    by_id: dict[int, str | None] = {}
    for row in rows:
        if isinstance(row, dict):
            by_id[row["request_id"]] = row.get("raw_title")
        else:
            by_id[row[0]] = row[1]
    for rid in uniq:
        title = by_id.get(rid)
        if rid not in by_id:
            continue  # missing refs handled by gate 7
        if is_mechanically_excluded(title):
            return False, f"request {rid} is mechanically excluded ({title!r})"
    return True, None


def _check_dup_add_ref(
    conn, request_id: int, ref_id: int, *, expect_same_problem: bool, parsed: dict,
) -> tuple[bool, str | None]:
    """Same unit, not closed; same_problem for duplicate, different for addition."""
    from .context_builder import is_mechanically_excluded, problem_text, same_problem

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT request_id, unit_id, status::text AS status,
                       raw_title, problems, problem_summary
                FROM maintenance_request WHERE request_id = %s
                """,
                (request_id,),
            )
            cur_row = cur.fetchone()
            cur.execute(
                """
                SELECT request_id, unit_id, status::text AS status,
                       raw_title, problems, problem_summary
                FROM maintenance_request WHERE request_id = %s
                """,
                (ref_id,),
            )
            ref_row = cur.fetchone()
    except Exception as exc:
        return False, f"DB lookup failed: {exc}"

    if cur_row is None:
        return False, f"request {request_id} not found"
    if ref_row is None:
        return False, f"referenced request {ref_id} not found"

    def _get(row, key, idx):
        if isinstance(row, dict):
            return row.get(key)
        return row[idx]

    cur_unit = _get(cur_row, "unit_id", 1)
    ref_unit = _get(ref_row, "unit_id", 1)
    ref_status = _get(ref_row, "status", 2)
    ref_title = _get(ref_row, "raw_title", 3)
    if is_mechanically_excluded(ref_title):
        return False, f"referenced request {ref_id} is mechanically excluded"
    if ref_status == "closed":
        return False, f"referenced request {ref_id} is closed"
    if cur_unit is not None and ref_unit is not None and cur_unit != ref_unit:
        return False, f"referenced request {ref_id} is not the same unit"

    # Prefer model title/problems for the incoming call; DB for the open peer.
    incoming = problem_text({
        "title": parsed.get("title"),
        "problems": parsed.get("problems"),
        "raw_title": _get(cur_row, "raw_title", 3),
        "problem_summary": _get(cur_row, "problem_summary", 5),
    })
    peer = problem_text({
        "raw_title": _get(ref_row, "raw_title", 3),
        "problems": _get(ref_row, "problems", 4),
        "problem_summary": _get(ref_row, "problem_summary", 5),
    })
    is_same = same_problem(incoming, peer)
    if expect_same_problem and not is_same:
        return False, f"duplicate requires same problem as #{ref_id}"
    if not expect_same_problem and is_same:
        return False, f"addition requires a different problem than #{ref_id}"
    return True, None


if __name__ == "__main__":
    _BASE = {
        "verdict": "single", "duplicate_of_request_id": None, "addition_to_request_id": None,
        "title": "Robinet qui fuit", "problems": ["Fuite sous le lavabo"],
        "entry_permission": None, "urgency_tier": None,
        "complexity_tier": "C1", "congestion_level": "N2",
        "time_estimate_bucket": "UNDER_30_MIN", "delegable_status": "YES",
        "report_status": "CAN_WAIT", "routing_rule": "A1", "subcontractor_name": None,
        "vendor_id": None, "synergy_request_ids": [], "other_notes": None,
        "recommended_tasks": [{"description": "Réparer le robinet"}],
    }

    def chk(label, d, expected, conn=None, rid=1):
        r, detail = validate(d, conn, rid)
        status = "PASS" if r == expected else "FAIL"
        print(f"{status}: {label} → {r}" + (f" ({detail})" if r != expected else ""))
        assert r == expected, f"Expected {expected}"

    chk("clean response",        _BASE, "accepted")
    chk("heating failure flag",  {**_BASE, "heating_failure": True}, "accepted")
    chk("single without tasks",  {**_BASE, "recommended_tasks": []}, "rejected_missing_recommended_tasks")
    chk("assignee field",        {**_BASE, "assignee": "Jean Tremblay"}, "rejected_no_assignee_field")
    chk("currency in problems",  {**_BASE, "problems": ["Loyer 500$ impayé"]}, "rejected_financial_content_problems")
    # Gate 3 — financial terms
    chk("financial term loyer",  {**_BASE, "other_notes": "Voir pour le loyer"},     "rejected_financial_content")
    chk("depot with amount",     {**_BASE, "other_notes": "Dépôt de 500$ requis"},   "rejected_financial_content")
    chk("depot montant",         {**_BASE, "other_notes": "dépôt: voir montant dû"}, "rejected_financial_content")
    chk("depot no context",      {**_BASE, "other_notes": "Dépôt de trousseau de clés"}, "accepted")
    chk("home depot price",      {**_BASE, "other_notes": "pièce vendue chez Home Depot (~15 $)"}, "accepted")
    # Gate 4 — access codes require digit near context term
    chk("code colon digit",      {**_BASE, "entry_permission": "code: 4821"},                        "rejected_access_code_content")
    chk("code clavier",          {**_BASE, "entry_permission": "le code du clavier est 4821"},       "rejected_access_code_content")
    chk("boite combinaison",     {**_BASE, "entry_permission": "boîte à clé #3 — combinaison 7729"},"rejected_access_code_content")
    chk("NIP porte",             {**_BASE, "other_notes": "NIP de la porte : 1234"},                 "rejected_access_code_content")
    chk("building number",       {**_BASE, "title": "2160-4 Cardinal-Villeneuve: Robinet"},          "accepted")
    chk("civic addr near serrure",{**_BASE, "other_notes": "serrure principale 3485-103 — historique"}, "accepted")
    chk("request ref near boite", {**_BASE, "other_notes": "#7722 (boîte à clés, 2 juil, réglé) — suivi"}, "accepted")
    chk("year in text",          {**_BASE, "problems": ["Fin de bail le 2026-08-31"]},               "accepted")
    chk("year near access term", {**_BASE, "other_notes": "Serrure à vérifier avant 2026-09-15"},    "accepted")
    chk("request id ref",        {**_BASE, "problems": ["voir demande originale #7042 du 10 juil"]}, "accepted")
    chk("du addr near keybox",   {**_BASE, "other_notes": "clés dans la keybox 2 du 3094 Châtelets — standard"}, "accepted")
    chk("au addr near serrure",  {**_BASE, "other_notes": "serrure externe de l'immeuble au 5875 Costebelle"}, "accepted")
    chk("depot dropoff paiement",{**_BASE, "problems": ["Paiement reçu. Accès autorisé pour dépôt sans présence du locataire."]}, "accepted")
    # Gate 5+
    chk("internal vocab",        {**_BASE, "other_notes": "Appliquer règle 6"}, "rejected_internal_vocabulary")
    chk("routing A2 no gym",     {**_BASE, "routing_rule": "A2", "subcontractor_name": "Duclos"},              "rejected_routing_inconsistent")
    chk("routing A3 no sub",     {**_BASE, "routing_rule": "A3", "subcontractor_name": None},                  "rejected_routing_inconsistent")
    chk("routing A3 body gym",   {**_BASE, "routing_rule": "A3", "subcontractor_name": "Body Gym"},            "rejected_routing_inconsistent")
    chk("A0 with subcontractor", {**_BASE, "routing_rule": "A0", "subcontractor_name": "H2Pro (piscine)"},     "accepted")
    chk("A1 with subcontractor", {**_BASE, "routing_rule": "A1", "subcontractor_name": "H2Pro"},               "rejected_routing_inconsistent")
    chk("addition missing ref",  {**_BASE, "verdict": "addition", "addition_to_request_id": None},    "rejected_invalid_addition_ref")
    chk("addition self-ref",     {**_BASE, "verdict": "addition", "addition_to_request_id": 1},       "rejected_invalid_addition_ref", rid=1)
    # Gate 5 — parking bay labels (Fix 1)
    chk("parking stationnement A5",   {**_BASE, "title": "Activation borne recharge stationnement A5 (temporaire)"}, "accepted")
    chk("parking borne A5 notes",     {**_BASE, "other_notes": "Clé borne stationnement A5 à programmer"}, "accepted")
    chk("A5 sector label still fires",{**_BASE, "other_notes": "Périmètre A5 rive-sud — immeuble attitré"}, "rejected_internal_vocabulary")
    # Gate 4 — fiche technique cross-references (Fix 2)
    chk("fiche ref before digit",     {**_BASE, "other_notes": "Boîte à clé : voir fiche Chamonix 1175 pour accès"}, "accepted")
    chk("fiche ref after digit",      {**_BASE, "other_notes": "Fiche Sully 7885 (boîte à clé dans la fiche)"}, "accepted")
    print("\nAll gates: PASS")
