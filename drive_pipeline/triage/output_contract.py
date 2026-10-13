"""
Output contract parser and validation gates for the AI triage service.

Gates run in order; first failure wins. A response that violated a gate is
not sanitised — it is rejected entirely and the caller decides on retry.
"""
from __future__ import annotations

import json
import re


class ValidationError(Exception):
    pass


OUTPUT_SCHEMA = {
    "verdict": "single | duplicate | addition",
    "duplicate_of_request_id": "int | null",
    "addition_to_request_id": "int | null",
    "title": "str",
    "problems": "list[str]",
    "entry_permission": "str | null",
    "animals": "str | null",
    "urgency_tier": "AJD | null",
    "complexity_tier": "C1|C2|C3|C4",
    "congestion_level": "N1|N2|N3|N4|N5",
    "time_estimate_bucket": "UNDER_30_MIN|MIN30_TO_1H|H1_TO_2H|H2_TO_4H|HALF_DAY_PLUS|TBD_ON_SITE",
    "delegable_status": "YES|NO|CONDITIONAL",
    "report_status": "CANNOT_WAIT|SUPERVISOR_DISCRETION|CAN_WAIT_SHORT_TERM|CAN_WAIT|NOT_APPLICABLE",
    "routing_rule": "A0|A1|A2|A3|A3b|A4|A5",
    "subcontractor_name": "str | null",
    "vendor_id": "int | null",
    "synergy_request_ids": "list[int]",
    "other_notes": "str | null",
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


def _text_fields(parsed: dict) -> list[str]:
    out = []
    for key in ("title", "entry_permission", "animals", "other_notes"):
        v = parsed.get(key)
        if isinstance(v, str):
            out.append(v)
    for p in parsed.get("problems", []):
        if isinstance(p, str):
            out.append(p)
    return out


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


def validate(parsed: dict, conn, request_id: int) -> tuple[str, str | None]:
    """
    Run all gates in order. Returns (result, detail).
    result: 'accepted' | 'rejected_<gate>' | 'error'
    detail: None on accept, rejection reason otherwise.
    """
    # Gate 1 — no assignee field (rule 20/37)
    if any("assign" in k.lower() for k in parsed):
        return "rejected_no_assignee_field", "Response contains an assignee field"

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

    # Gate 6 — routing_rule consistent with subcontractor_name (rule 6b)
    routing = parsed.get("routing_rule", "")
    sub = parsed.get("subcontractor_name") or ""
    if routing == "A2":
        if not re.search(r"body\s*gym|gym", sub, re.IGNORECASE):
            return "rejected_routing_inconsistent", f"A2 requires Body Gym, got {sub!r}"
    elif routing in ("A3", "A3b"):
        if not sub or re.search(r"body\s*gym", sub, re.IGNORECASE):
            return "rejected_routing_inconsistent", f"{routing} requires non-Body-Gym subcontractor, got {sub!r}"
    elif routing == "A1":
        # A1 = C1 tasks (key deposits, simple checks) — no external vendor plausible
        if sub and not sub.lower().startswith("non"):
            return "rejected_routing_inconsistent", f"A1 expects no subcontractor, got {sub!r}"
    # A0 + subcontractor is valid: guide defines A0 as coordinator for subcontractor work
    # (section 6b: "coordination d'un sous-traitant (Body Gym, Duclos, Fortin, Éric…)")

    # Gate 7 — addition verdict must reference a non-closed request (rule 12)
    if parsed.get("verdict") == "addition":
        ref_id = parsed.get("addition_to_request_id")
        if not isinstance(ref_id, int):
            return "rejected_invalid_addition_ref", "addition_to_request_id missing or not an integer"
        if ref_id == request_id:
            return "rejected_invalid_addition_ref", "addition_to_request_id references the request itself"
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status FROM maintenance_request WHERE request_id = %s",
                        (ref_id,),
                    )
                    row = cur.fetchone()
                if row is None:
                    return "rejected_invalid_addition_ref", f"addition_to_request_id {ref_id} not found"
                status = row[0] if isinstance(row, tuple) else row["status"]
                if status == "closed":
                    return "rejected_invalid_addition_ref", f"addition_to_request_id {ref_id} is closed"
            except Exception as exc:
                return "error", f"DB lookup failed: {exc}"

    return "accepted", None


if __name__ == "__main__":
    _BASE = {
        "verdict": "single", "duplicate_of_request_id": None, "addition_to_request_id": None,
        "title": "Robinet qui fuit", "problems": ["Fuite sous le lavabo"],
        "entry_permission": None, "animals": None, "urgency_tier": None,
        "complexity_tier": "C1", "congestion_level": "N2",
        "time_estimate_bucket": "UNDER_30_MIN", "delegable_status": "YES",
        "report_status": "CAN_WAIT", "routing_rule": "A1", "subcontractor_name": None,
        "vendor_id": None, "synergy_request_ids": [], "other_notes": None,
    }

    def chk(label, d, expected, conn=None, rid=1):
        r, detail = validate(d, conn, rid)
        status = "PASS" if r == expected else "FAIL"
        print(f"{status}: {label} → {r}" + (f" ({detail})" if r != expected else ""))
        assert r == expected, f"Expected {expected}"

    chk("clean response",        _BASE, "accepted")
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
