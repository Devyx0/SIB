"""
parse_calendar_requests.py — DRY RUN: pull 45-day Google Calendar event window and
parse maintenance_request fields.

Does NOT write to Supabase. Prints format breakdown, 5 sample events with full
field extraction and provenance, unknown employee codes, and unmatched buildings.

Run:
    uv run python -m drive_pipeline.ingestion.parse_calendar_requests
"""

from __future__ import annotations

import html
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from drive_pipeline.table_fondamentale.table_fondamentale import TABLE_FONDAMENTALE
from drive_pipeline.ingestion.provenance import log_provenance, flush

# ── Config ────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar.readonly",
]

MAIN_CAL    = "maintenance@sibelanger.com"
ST_MAJ_CAL  = ("8d55093fb316f4eda1504cd853462fea86f64a4e78556e0924f3c994d2c63bf8"
                "@group.calendar.google.com")

CALENDAR_IDS = {
    "main":    MAIN_CAL,
    "st_maj":  ST_MAJ_CAL,
}

# ── Employee roster (from secteurs-et-equipe.md) ──────────────────────────────

KNOWN_EMPLOYEE_CODES: set[str] = {
    # Direction / coordination
    "CHBE", "CALE", "CHGE", "PISI", "SETO", "DISP",
    # Technical / coordinator
    "NIRO", "SV", "VIBR",
    # Workers
    "ALLE", "FRLA", "JFME", "MABL", "PB", "SAHA", "SIDE", "STLE", "ZARO", "JCS",
    # Worker-companies
    "MITR", "CHFE", "CHSL", "BESA", "ALTH", "MACH", "KEPO",
    # Confirmed from 45-day corpus (2026-09-28): on-site cleaners / field workers
    "JOTH",  # 350 Ste-Foy on-site; "elle a fait le ménage" in field notes
    "MAMU",  # turnover cleaner; "Menage fait par MAMU" in gravity_raw
    "RIPE",  # St-Jean field worker; first-person field notes
    "NAGA",  # 315 St-Jean turnover cleaner; "EDL Fait NAGA" in gravity_raw
    # Seen in corpus — unknown, logged as gap
    "AZBE", "CFD",
    # Documented in employee table but missing from this set:
    "FLNA", "FRBE", "MAPO",
    # Inferred from March–August 2026 corpus (employee_id 44–54);
    # source_confidence='inferred_from_calendar' — not in Contacts file
    "MAPI", "GELE", "ANSI", "YVLI", "MAMO", "JMBO", "ALHA",
    "GALS", "FRLE", "CH", "NICO",
    # CALLE: probable typo for CALE; strips from address, raw preserved in assigned_employee_code_raw
    "CALLE",
}

# Tokens stripped from the address-parsing path but NOT written to assigned_employee_code_raw.
# The set name says "vendor" but it doubles as a general strip-but-don't-assign list:
# MAXI/TK/ERIC/PDQ are genuine vendors; SAC is an inter-code dispatch annotation (not a person);
# TEST is a test-event token. Use this set for anything that must be stripped without creating
# an employee assignment, regardless of its semantic category.
KNOWN_VENDOR_CODES: set[str] = {
    "MAXI",  # ascenseurs (TK/MAXI per secteurs-et-equipe.md)
    "TK",    # ascenseurs (TK/MAXI per secteurs-et-equipe.md)
    "ERIC",  # extermination (Éric — appears uppercase in some titles)
    "PDQ",   # garage door vendor at Châtelets (not in doc; always for porte-de-garage events)
    "SAC",   # inter-code dispatch annotation — always after a primary assignee, never a person
    "TEST",  # test-event token, not a vendor or employee
}

# Urgency codes that can appear after the employee code in the title
URGENCY_TOKENS = {"ajd", "urgt", "urgent", "dem", "semaine", "2sem", "mois", "report"}

# ── Translation ───────────────────────────────────────────────────────────────

# Prose fields that should be translated French → English before writing to DB.
# Fields NOT in this list (names, phones, codes, links, addresses) are preserved verbatim.
_TRANSLATE_PROSE_FIELDS = [
    "problems", "tri", "report", "entry_permission", "animals",
    "historique_raw", "bail_raw", "autres_notes", "embourbement",
    "delegable", "doublons", "synergie_raw",
    "message",  # Gravity Forms free-text field
]

_TRANSLATION_SYSTEM = """\
You are a precise French → English translation engine for property management records.

Apply these rules in strict priority order:

PRESERVE exactly as-is (status: "preserved_code_or_name"):
- Phone numbers, alarm codes, access codes, door codes, PIN numbers
- Proper nouns: street names, building names, company/vendor names
- Client/account reference codes
- Measurements and dimensions — preserve numbers and units exactly
- Short ALL-CAPS abbreviations (AV, AR, CE, SS, SB, etc.) — physical labels on keys/panels
- ANY acronym or abbreviation you cannot confidently expand to full English
- Login credentials (usernames, passwords)
- Numeric-only values, dates, years
- Names of people (tenants, employees, technicians)

TRANSLATE the prose (status: "translated"):
- Problem descriptions, triage decisions, instructions, notes
- For MIXED fields: translate only the prose portions; leave codes/names/numbers verbatim

NO-CHANGE (status: "no_change"):
- Field is already fully in English

LOW CONFIDENCE (status: "preserved_low_confidence"):
- When not fully confident the translation is operationally safe
- Return the original French text UNCHANGED
- Never guess — wrong translations of security codes or access instructions cause harm

CRITICAL (F8/F9): tenant names, phone numbers, unit numbers, codes are PII/credentials — NEVER translate or alter them.

OUTPUT: Return ONLY a valid JSON array, one object per input item, same order as input:
[{"idx": <int>, "translation": "<text>", "status": "translated|preserved_code_or_name|no_change|preserved_low_confidence"}, ...]"""

_anthropic_client: Any = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic  # noqa: PLC0415
        extra: dict = {}
        wsid = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
        if wsid:
            extra["anthropic-workspace-id"] = wsid
        _anthropic_client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            default_headers=extra if extra else None,
        )
    return _anthropic_client


def _translate_prose_fields(fields: dict) -> None:
    """Translate prose fields in-place (French → English). Preserves names/phones/codes."""
    items = [
        {"idx": i, "field": k, "value": fields[k]}
        for i, k in enumerate(_TRANSLATE_PROSE_FIELDS)
        if fields.get(k)
    ]
    if not items:
        return
    try:
        client = _get_anthropic_client()
        payload = json.dumps(
            [{"idx": it["idx"], "field": it["field"], "value": it["value"]} for it in items],
            ensure_ascii=False,
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=_TRANSLATION_SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).rsplit("```", 1)[0].strip()
        results = json.loads(raw)
        by_idx = {r["idx"]: r["translation"] for r in results if isinstance(r, dict)}
        for it in items:
            if it["idx"] in by_idx:
                fields[it["field"]] = by_idx[it["idx"]]
    except Exception:
        pass  # on failure keep originals — never lose data


# ── Exclusion helpers ─────────────────────────────────────────────────────────

_WASTE_RE = re.compile(
    r"collecte|mati[eè]res?\s+r[eé]siduelles|recyclage\s+ordi|ramassage",
    re.IGNORECASE,
)
_BLDG_LIST_RE = re.compile(r"liste\s+d.immeubles?", re.IGNORECASE)


def _is_excluded(event: dict) -> tuple[bool, str]:
    """Return (excluded, reason) for events that must be skipped."""
    title = event.get("summary", "")
    # Administrative / vacation prefix
    if title.startswith("!"):
        return True, "admin_prefix_!"
    # In-execution prefix — "X " (space) or "X" alone or "XCODE" (no space, e.g. XSAHA)
    if re.match(r"^X(?:\s|[A-Z]|$)", title):
        return True, "in_execution_prefix_X"
    # Recurring series instance
    if event.get("recurringEventId"):
        return True, "recurring_series"
    # Waste collection
    if _WASTE_RE.search(title):
        return True, "waste_collection"
    # Building list events
    if _BLDG_LIST_RE.search(title):
        return True, "building_list"
    return False, ""


# ── Auth ─────────────────────────────────────────────────────────────────────

def _get_creds() -> Credentials:
    token_path = ROOT / "token.json"
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(ROOT / "credentials.json"), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


# ── Calendar pull ─────────────────────────────────────────────────────────────

def _pull_events(service, cal_id: str, start: datetime, end: datetime) -> list[dict]:
    """Pull all events in [start, end) with full pagination."""
    time_min = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    events: list[dict] = []
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=250,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


# ── HTML stripping ────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._in_anchor = False
        self._anchor_href = ""
        self._anchor_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._in_anchor = True
            self._anchor_href = d.get("href", "")
            self._anchor_text = ""
        elif tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "a":
            self._parts.append(f"[LINK:{self._anchor_href}|{self._anchor_text}]")
            self._in_anchor = False

    def handle_data(self, data):
        if self._in_anchor:
            self._anchor_text += data
        else:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _strip_html(raw: str) -> str:
    """Strip HTML tags and decode entities; preserve newlines from <br> and links as [LINK:href|text]."""
    raw = html.unescape(raw)
    p = _TextExtractor()
    p.feed(raw)
    return p.get_text()


# ── Title parser ──────────────────────────────────────────────────────────────

# Matches: CODE [urgency] civic[-unit] street: problem
# CODE: 2–5 uppercase letters, optionally with hyphen (JC-S)
_CODE_RE   = re.compile(r"^([A-Z]{2,5}(?:-[A-Z])?)\s+")
_URG_RE    = re.compile(r"^(ajd|urgt|urgent|dem|semaine|2sem|mois|report)\s+", re.IGNORECASE)
# civic: digits, optional range/multi with hyphens, optional trailing letter (e.g. 220-460B)
# unit: optional second block after the last dash that could be a unit (e.g. 640-101 → unit 101)
# street: everything up to the first ":"
_ADDR_RE   = re.compile(
    r"^([\d][\d\-]*(?:\s+[àaA]\s+[\d\-]+)?[A-Za-z]?)\s+(.*?):\s*(.*?)$",
    re.DOTALL,
)
# Mixed-case / multi-word vendor names that appear as the second title token
_VENDOR_NAME_RE = re.compile(
    r"^(?:[ÉE]ric|[ÉE]lectroDB|BoucherLortie|Boucher\s*Lortie|"
    r"Fortin|Wifi\s*Qu[eé]bec|WifiQu[eé]bec|VilleQc|"
    r"Coinamatic|Duclos|Davor|4\s*Saisons|Soluclim|EnviroConfort|"
    r"AlarmeExpert|H2Pro|Labrecque|Matrec|Osen|Newtech)\s+",
    re.IGNORECASE,
)
# Non-person keywords that appear between the code strip and the civic number
_PRECIVIC_RE = re.compile(
    r"^(?:ajout[A-Za-z]*|Doublons?|DOUBLON(?:\s+POTENTIEL)?|Terrain|Urgence)\s*[-–]?\s*",
    re.IGNORECASE,
)


def _parse_title(title: str) -> dict:
    result: dict[str, Any] = {
        "raw_title": title,
        "employee_code": None,
        "employee_known": None,
        "urgency": None,
        "civic": None,
        "unit": None,
        "street": None,
        "problem_summary": None,
    }
    rest = title

    # 1. Employee code (skip if first token is actually an urgency token like AJD)
    m = _CODE_RE.match(rest)
    if m:
        code = m.group(1).replace("-", "")  # normalize JC-S → JCS for lookup
        if code.lower() not in URGENCY_TOKENS:
            if code not in KNOWN_VENDOR_CODES:
                result["employee_code"] = m.group(1)
                result["employee_known"] = code in KNOWN_EMPLOYEE_CODES
            rest = rest[m.end():]
            rest = re.sub(r"^\([^)]+\)\s*", "", rest)

    # Multi-pass: strip employee codes, vendor codes, urgency tokens, vendor names,
    # and pre-civic keywords in any interleaved order until nothing changes.
    # Handles patterns like "CODE1 ajd CODE2 addr", "CODE AJOUT addr", "CODE Fortin addr".
    _changed = True
    while _changed:
        _changed = False
        # Uppercase codes (employee + vendor + urgency-as-code e.g. "AJD")
        while True:
            m2 = _CODE_RE.match(rest)
            if not m2:
                break
            c2 = m2.group(1).replace("-", "")
            if c2 in KNOWN_EMPLOYEE_CODES or c2 in KNOWN_VENDOR_CODES or c2.lower() in URGENCY_TOKENS:
                rest = rest[m2.end():]
                rest = re.sub(r"^\([^)]+\)\s*", "", rest)
                _changed = True
            else:
                break
        # Lowercase / mixed-case urgency token
        m_urg = _URG_RE.match(rest)
        if m_urg:
            result["urgency"] = m_urg.group(1).lower()
            rest = rest[m_urg.end():]
            _changed = True
            continue
        # Mixed-case vendor names (not caught by _CODE_RE)
        m_v = _VENDOR_NAME_RE.match(rest)
        if m_v:
            rest = rest[m_v.end():]
            _changed = True
            continue
        # Pre-civic keywords (AJOUT, Terrain, Doublons, etc.)
        m_k = _PRECIVIC_RE.match(rest)
        if m_k:
            rest = rest[m_k.end():]
            _changed = True

    # 2. Address + problem
    m = _ADDR_RE.match(rest)
    if m:
        civic_raw = m.group(1).strip()
        street_raw = m.group(2).strip()
        result["problem_summary"] = m.group(3).strip() or None
        # Try to split civic from unit: last dash-separated segment that looks like a unit
        parts = civic_raw.split("-")
        if len(parts) >= 2 and len(parts[-1]) <= 4:
            # Heuristic: if last segment is short (≤4 digits), treat as unit
            result["unit"] = parts[-1]
            result["civic"] = "-".join(parts[:-1])
        else:
            result["civic"] = civic_raw
        result["street"] = street_raw if street_raw else None
    elif ":" in rest:
        # No address match but there's still a colon separator
        addr_part, _, prob_part = rest.partition(":")
        result["problem_summary"] = prob_part.strip() or None
        result["street"] = addr_part.strip() or None

    return result


# ── Body format detection & parsing ───────────────────────────────────────────

_V10_MARKER  = re.compile(r"<b><u>(?:FOLLOW-UP TERRAIN|PROBL[EÈ]MES)", re.IGNORECASE)
# Plain-text v10: section labels appear alone on a line, no HTML tags.
_V10_PLAIN_MARKER = re.compile(
    r"^(?:FOLLOW-UP TERRAIN|PROBL[EÈ]MES\s*:|PERMISSION D'ENTR[EÉE]+\s*:)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# Legacy fallback: structured notes that missed both primary markers because:
#   - section headings lack <b><u> wrapping (no _V10_MARKER match)
#   - <br> tags embed on the same \n-line as section labels (no _V10_PLAIN_MARKER match)
#   - QUOI FAIRE used instead of PROBLÈMES (older label from before guide rule 4)
# SECTION COORDOS is present in all structured notes and is the safest single trigger.
# Applied AFTER both primary markers so it can never reclassify a correctly-detected event.
# Dry-run confirmed: 120 unparsed rows match; 0 already-classified events are affected.
_V10_LEGACY_MARKER = re.compile(r"SECTION COORDOS", re.IGNORECASE)

_BEL_START   = re.compile(r"---\s*B[EÉ]LANGER\s+(.+?)\s*---", re.IGNORECASE)
_BEL_END     = re.compile(r"---\s*FIN\s+B[EÉ]LANGER\b.*?---", re.IGNORECASE)

# Section label regex — matches stripped text after HTML normalisation.
# Covers v10.5 labels (SECTION TERRAIN, QUOI FAIRE) as well as v10.6 labels.
_SEC_LABEL_RE = re.compile(
    r"^(FOLLOW-UP TERRAIN|SECTION TERRAIN|QUOI FAIRE\s*:|PROBL[EÈ]MES\s*:|PERMISSION D'ENTR[EÉE]+\s*:|ANIMAUX\s*:"
    r"|OCCUPANTS\s*:|BAIL\s*:|FICHE TECHNIQUE\s*:|HISTORIQUE\s*:"
    r"|SECTION COORDOS|TRI\s*:|D[EÉ]L[EÉ]GABLE\s*:|REPORT\s*:"
    r"|DOUBLONS\s*:|CALLS ACTIFS\s*/\s*SYNERGIE\s*:|UNIT[EÉ]\s*:|PROJET\s*:"
    r"|TEMPS\s*:|COMPLEXIT[EÉ]\s*:|SOUS-TRAITANT\s*:|ASSIGNATION PROPOS[EÉ]E\s*:"
    r"|ENTENTE LOCATAIRE[^:]*:|AUTRES NOTES\s*:|EMBOURBEMENT\s*:)"
    r"\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

_LINK_RE = re.compile(r"\[LINK:([^\|]*)\|([^\]]*)\]")
_FT_LINK_RE = re.compile(r"\[LINK:(https?://[^\|]+)\|([^\]]*)\]")
_CAL_LINK_RE = re.compile(r"\[LINK:(https://[^\|]+)\|[^\]]*\]")


def _extract_eid(url: str) -> str | None:
    """Extract the base64 eid parameter from a Google Calendar URL.

    Handles two forms:
      • Direct:        https://www.google.com/calendar/event?eid=<b64>
      • Double-encoded: https://www.google.com/url?q=https://...?eid=<b64>
    """
    import urllib.parse as _up
    parsed = _up.urlparse(url)
    qs = _up.parse_qs(parsed.query)
    direct = qs.get("eid", [None])[0]
    if direct:
        return direct
    # Double-encoded: outer URL is google.com/url, inner URL is in q=
    inner = qs.get("q", [None])[0]
    if inner:
        return _up.parse_qs(_up.urlparse(inner).query).get("eid", [None])[0]
    return None


def _parse_event_id(b64: str) -> str | None:
    """Decode a Calendar eid and return the bare event ID (before the space/calendar suffix)."""
    import base64 as _b64
    try:
        padded = b64 + "=" * (-len(b64) % 4)
        decoded = _b64.b64decode(padded).decode("utf-8", errors="replace")
        return decoded.split(" ")[0].strip() or None
    except Exception:
        return None


def resolve_url_refs(conn, request_ids: list[int]) -> dict[str, int]:
    """Resolve calendar URL references in historique_raw/doublons/synergie_raw for the given
    request_ids and write results to maintenance_request_history, duplicate_of_request_id,
    and synergy_request_ids.

    Designed for a second-pass call after all rows in a batch are inserted, so intra-batch
    references resolve correctly. Returns counts: {'history': N, 'duplicate': N, 'synergy': N}.

    On a fresh ingest, references to tickets OUTSIDE the current DB (e.g. events from a
    prior window that haven't been ingested yet) are silently skipped — they appear as
    "outside window" and their target_pk stays NULL. Widening the backfill window is the
    only way to resolve those; see docs/project_status.md for the quantification.
    """
    from psycopg2.extras import execute_values

    cur = conn.cursor()

    # Build event_id → request_id lookup from the full DB (includes current batch)
    cur.execute("SELECT request_id, html_link FROM maintenance_request WHERE html_link IS NOT NULL")
    eid_to_req: dict[str, int] = {}
    for rid, lnk in cur.fetchall():
        b64 = _extract_eid(lnk)
        if b64:
            evid = _parse_event_id(b64)
            if evid:
                eid_to_req[evid] = rid

    cur.execute(
        "SELECT request_id, historique_raw, doublons, synergie_raw "
        "FROM maintenance_request WHERE request_id = ANY(%s)",
        (request_ids,),
    )
    rows = cur.fetchall()

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_id = cur.fetchone()[0]

    def _next_prov():
        nonlocal prov_id
        prov_id += 1
        return prov_id

    def _resolve_urls(val: str | None) -> list[int]:
        if not val:
            return []
        targets = []
        for url in _CAL_LINK_RE.findall(val):
            b64 = _extract_eid(url)
            evid = _parse_event_id(b64) if b64 else None
            tgt = eid_to_req.get(evid) if evid else None
            if tgt and tgt not in targets:
                targets.append(tgt)
        return targets

    counts = {"history": 0, "duplicate": 0, "synergy": 0}
    hist_rows, hist_prov = [], []
    doub_prov, syn_prov = [], []

    for rid, hist_raw, doub_raw, syn_raw in rows:
        # historique_raw → maintenance_request_history
        for tgt in _resolve_urls(hist_raw):
            if tgt != rid:
                hist_rows.append((rid, tgt, "prior_ticket"))
                hist_prov.append((_next_prov(), "maintenance_request_history", None,
                                  "referenced_request_id", "derived", None, "historique_raw",
                                  None, None, "historique_raw", str(tgt), str(tgt), None))

        # doublons → duplicate_of_request_id (first match wins per row)
        doub_targets = _resolve_urls(doub_raw)
        if doub_targets:
            tgt = doub_targets[0]
            cur.execute(
                "UPDATE maintenance_request SET duplicate_of_request_id = %s "
                "WHERE request_id = %s AND duplicate_of_request_id IS NULL",
                (tgt, rid),
            )
            if cur.rowcount:
                counts["duplicate"] += 1
                doub_prov.append((_next_prov(), "maintenance_request", rid,
                                   "duplicate_of_request_id", "derived", None, "doublons",
                                   None, None, "doublons", str(tgt), str(tgt), None))

        # synergie_raw → synergy_request_ids (integer[])
        syn_targets = _resolve_urls(syn_raw)
        if syn_targets:
            cur.execute(
                "UPDATE maintenance_request SET synergy_request_ids = %s "
                "WHERE request_id = %s AND synergy_request_ids IS NULL",
                (syn_targets, rid),
            )
            if cur.rowcount:
                counts["synergy"] += 1
                arr_str = "{" + ",".join(str(t) for t in syn_targets) + "}"
                syn_prov.append((_next_prov(), "maintenance_request", rid,
                                  "synergy_request_ids", "derived", None, "synergie_raw",
                                  None, None, "synergie_raw", arr_str, arr_str, None))

    if hist_rows:
        execute_values(cur,
            "INSERT INTO maintenance_request_history "
            "(request_id, referenced_request_id, relation_type) VALUES %s ON CONFLICT DO NOTHING",
            hist_rows, page_size=200)
        # Backfill target_pk
        cur.execute("SELECT history_id, request_id, referenced_request_id FROM maintenance_request_history")
        id_map = {(r, t): h for h, r, t in cur.fetchall()}
        hist_prov = [(p[0], p[1], id_map.get((src, tgt), None), *p[3:])
                     for p, (src, tgt, _) in zip(hist_prov, hist_rows)]
        counts["history"] = cur.rowcount

    all_prov = hist_prov + doub_prov + syn_prov
    if all_prov:
        execute_values(cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            all_prov, page_size=200)

    return counts


# ── Unit resolution ────────────────────────────────────────────────────────────

_CIVIC_APT_LABEL_RE = re.compile(r'^(\d[\d\-]*[A-Za-z]?)\s*[-–]\s*(\d+[A-Za-z]?)(?:\s+.*)?$')
_CIVIC_FROM_RUE_RE  = re.compile(r'^(\d[\d\-]*[A-Za-z]?)')


def build_unit_index(conn) -> dict:
    """Build lookup tables for unit_id resolution from unit_label + building_id.

    Returns:
      'civic_apt': {(building_id, civic_str, apt_str): unit_id}
      'apt_uniq':  {(building_id, apt_str): unit_id}  — only when exactly one candidate
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT unit_id, building_id, rue, numero_appartement "
        "FROM unit WHERE numero_appartement IS NOT NULL"
    )
    apt_multi: dict[tuple, list] = {}
    civic_apt_multi: dict[tuple, list] = {}

    for uid, bid, rue, apt in cur.fetchall():
        apt_s = str(apt)
        apt_multi.setdefault((bid, apt_s), []).append(uid)
        if rue:
            m = _CIVIC_FROM_RUE_RE.match(str(rue))
            if m:
                civic_apt_multi.setdefault((bid, m.group(1), apt_s), []).append(uid)

    return {
        "civic_apt": {k: v[0] for k, v in civic_apt_multi.items() if len(v) == 1},
        "apt_uniq":  {k: v[0] for k, v in apt_multi.items() if len(v) == 1},
    }


def resolve_unit_id(unit_label: str | None, building_id: int | None, unit_index: dict) -> int | None:
    """Resolve unit_label + building_id to a unit_id.

    Tier 1 — CIVIC-APT format: match on (building_id, civic, apt), civic from the
    first token of unit.rue. No fallback to apt-only on civic mismatch — large civic
    discrepancies indicate wrong building_id, not a format edge case.

    Tier 2 — number-only: match on (building_id, apt) only when unambiguous (exactly
    one unit has that numero_appartement in the building). Returns None for multi-address
    buildings where the same apt number appears in multiple streets.

    Returns None on ambiguity, no match, common-area labels, or missing inputs.
    """
    if not unit_label or building_id is None:
        return None
    lbl = unit_label.strip()
    m = _CIVIC_APT_LABEL_RE.match(lbl)
    if m:
        return unit_index["civic_apt"].get((building_id, m.group(1), m.group(2)))
    if re.match(r"^\d+$", lbl):
        return unit_index["apt_uniq"].get((building_id, lbl))
    return None


def _extract_v10_sections(lines: list[str]) -> dict[str, Any]:
    """Shared section accumulation core for HTML and plain-text v10 events.

    Takes a list of pre-processed plain text lines (HTML already stripped).
    Returns all v10 fields except 'format', 'signed_date', and 'gravity_raw'
    — callers set those since they depend on the full text, not individual lines.
    """
    fields: dict[str, Any] = {
        "problems":         None,
        "entry_permission": None,
        "animals":          None,
        "occupants_raw":    None,
        "bail_raw":         None,
        "ft_link":          None,
        "ft_name":          None,
        "historique_raw":   None,
        "tri":              None,
        "delegable":        None,
        "report":           None,
        "doublons":         None,
        "synergie_raw":     None,
        "unite":            None,
        "projet":           None,
        "temps":            None,
        "complexite":       None,
        "sous_traitant":    None,
        "assignation":      None,
        "autres_notes":     None,
        "embourbement":     None,
        "gravity_raw":      None,
        "signed_date":      None,
    }

    sections: dict[str, list[str]] = {}
    current_sec = None
    separator_count = 0
    in_gravity = False

    for line in lines:
        stripped = line.strip()
        if re.match(r"^=+$", stripped):
            separator_count += 1
            continue
        if separator_count >= 4 and not in_gravity and current_sec != "SECTION COORDOS":
            in_gravity = True

        m = _SEC_LABEL_RE.match(stripped)
        if m:
            label = re.sub(r"[:\s]+$", "", m.group(1)).upper().strip()
            remainder = m.group(2).strip()
            label = (label
                     .replace("PROBLÈMES", "PROBLEMES")
                     .replace("PROBLEMES", "PROBLEMES")
                     .replace("QUOI FAIRE", "PROBLEMES")  # v10.5 predecessor label (guide rule 4)
                     .replace("PERMISSION D'ENTRÉE", "PERMISSION")
                     .replace("PERMISSION D'ENTREE", "PERMISSION")
                     .replace("DÉLÉGABLE", "DELEGABLE")
                     .replace("DÉLÉGABLE", "DELEGABLE")
                     .replace("COMPLEXITÉ", "COMPLEXITE")
                     .replace("UNITÉ", "UNITE")
                     .replace("ÉLÉMENTS ACTIFS / SYNERGIE", "SYNERGIE")
                     )
            if "CALLS ACTIFS" in label or "SYNERGIE" in label:
                label = "SYNERGIE"
            current_sec = label
            sections.setdefault(label, [])
            if remainder:
                sections[label].append(remainder)
            in_gravity = False
        elif current_sec is not None and not in_gravity:
            sections.setdefault(current_sec, []).append(line)

    def _join(key) -> str | None:
        t = "\n".join(sections.get(key, [])).strip()
        return t or None

    fields["problems"]         = _join("PROBLEMES")
    fields["entry_permission"] = _join("PERMISSION")
    fields["animals"]          = _join("ANIMAUX")
    fields["occupants_raw"]    = _join("OCCUPANTS")
    fields["bail_raw"]         = _join("BAIL")
    fields["historique_raw"]   = _join("HISTORIQUE")
    fields["tri"]              = _join("TRI")
    fields["delegable"]        = _join("DELEGABLE")
    fields["report"]           = _join("REPORT")
    fields["doublons"]         = _join("DOUBLONS")
    fields["synergie_raw"]     = _join("SYNERGIE")
    fields["unite"]            = _join("UNITE")
    fields["projet"]           = _join("PROJET")
    fields["temps"]            = _join("TEMPS")
    fields["complexite"]       = _join("COMPLEXITE")
    fields["sous_traitant"]    = _join("SOUS-TRAITANT")
    fields["assignation"]      = _join("ASSIGNATION PROPOSEE")
    fields["autres_notes"]     = _join("AUTRES NOTES")
    fields["embourbement"]     = _join("EMBOURBEMENT")

    ft_raw = _join("FICHE TECHNIQUE")
    if ft_raw:
        lm = _FT_LINK_RE.search(ft_raw)
        if lm:
            fields["ft_link"] = lm.group(1)
            fields["ft_name"] = lm.group(2).strip() or None
        else:
            fields["ft_name"] = ft_raw

    return fields


def _v10_post_process(fields: dict, text: str) -> None:
    """Extract signed_date and gravity_raw from the full text string (shared by both v10 variants)."""
    bm = re.search(r"B[EÉ]LANGER\s+(\d+\s+\w+\s+\d{4})", text, re.IGNORECASE)
    if bm:
        fields["signed_date"] = bm.group(1)
    bel_idx = text.rfind("BÉLANGER")
    if bel_idx == -1:
        bel_idx = text.rfind("BELANGER")
    if bel_idx != -1:
        after = text[bel_idx:]
        nl = after.find("\n")
        if nl != -1:
            fields["gravity_raw"] = after[nl:].strip() or None


def _parse_v10(description: str) -> dict:
    """Parse v10.6 HTML format."""
    text = _strip_html(description)
    lines = [ln.rstrip() for ln in text.split("\n")]
    fields = _extract_v10_sections(lines)
    fields["format"] = "v10"
    _v10_post_process(fields, text)
    return fields


def _parse_v10_plaintext(description: str) -> dict:
    """Parse plain-text v10 format — same structure as v10 but delivered without HTML tags."""
    text = html.unescape(description)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG_RE.sub("", text)
    lines = [ln.rstrip() for ln in text.split("\n")]
    fields = _extract_v10_sections(lines)
    fields["format"] = "v10_plaintext"
    _v10_post_process(fields, text)
    return fields


def _parse_v10_legacy(description: str) -> dict:
    """Recover structured notes that missed both primary markers.

    Uses the same normalisation pipeline as _parse_v10_plaintext (<br>→\\n, HTML strip)
    which is sufficient for all three miss-reasons: bare <br> separators, QUOI FAIRE label,
    and the single FOLLOW-UP TERRAINj typo row. format='v10_legacy' distinguishes these
    from primary-marker detections in the DB.
    """
    fields = _parse_v10_plaintext(description)
    fields["format"] = "v10_legacy"
    return fields


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_compact_html(s: str) -> str:
    """Remove HTML tags and decode entities from compact-format field values."""
    s = html.unescape(s)
    s = _HTML_TAG_RE.sub("", s)
    return s.strip()


def _parse_belanger_compact(description: str) -> dict:
    """Parse compact '--- BÉLANGER date --- ... --- FIN BÉLANGER ---' format."""
    fields: dict[str, Any] = {"format": "belanger_compact"}

    m_start = _BEL_START.search(description)
    m_end   = _BEL_END.search(description)

    if not m_start:
        return fields

    fields["signed_date"] = m_start.group(1).strip()
    start_pos = m_start.end()
    end_pos   = m_end.start() if m_end else len(description)
    body = description[start_pos:end_pos].strip()

    # Extract fields by label: each label is on its own line, value follows on the same or next line
    # Labels known: AJD, ACCÈS, LOCATAIRE, BAIL, IMMEUBLE, CHAUFFAGE, FICHE TECHNIQUE,
    #               DOUBLONS, SYNERGIE, ASSIGNATION PROPOSÉE
    _FIELD_RE = re.compile(
        r"(AJD|ACC[EÈ]S|LOCATAIRE|BAIL|IMMEUBLE|CHAUFFAGE|FICHE TECHNIQUE|DOUBLONS|SYNERGIE|ASSIGNATION PROPOS[EÉ]E)\s*[:\-]?\s*",
        re.IGNORECASE,
    )
    field_map = {
        "AJD":    "problems",
        "ACCÈS":  "entry_permission",
        "ACCES":  "entry_permission",
        "LOCATAIRE": "occupants_raw",
        "BAIL":   "bail_raw",
        "IMMEUBLE": "building_raw",
        "CHAUFFAGE": "heating_raw",
        "FICHE TECHNIQUE": "ft_raw",
        "DOUBLONS": "doublons",
        "SYNERGIE": "synergie_raw",
        "ASSIGNATION PROPOSÉE": "assignation",
        "ASSIGNATION PROPOSEE": "assignation",
    }

    # Simple split: find each label, capture text until next label
    parts = _FIELD_RE.split(body)
    # parts = [pre_text, label1, value1, label2, value2, ...]
    i = 1  # skip pre_text at index 0
    while i < len(parts) - 1:
        label = parts[i].strip().upper()
        value = parts[i + 1].strip() if i + 1 < len(parts) else ""
        key = field_map.get(label)
        if not key:
            for k in field_map:
                if k in label:
                    key = field_map[k]
                    break
        if key:
            fields[key] = value or None  # store raw; HTML stripped at end
        i += 2

    # Extract FT link from raw value before HTML is stripped
    ft_raw_html = fields.get("ft_raw") or ""
    if ft_raw_html:
        lm = _FT_LINK_RE.search(ft_raw_html)  # [LINK:url|text] from _strip_html path
        if lm:
            fields["ft_link"] = lm.group(1)
            fields["ft_name"] = lm.group(2).strip() or None
        else:
            # Compact bodies may have raw <a href="..."> tags
            href_m = re.search(r'href="([^"]*https[^"]*)"', ft_raw_html)
            if href_m:
                fields["ft_link"] = href_m.group(1)
                text_m = re.search(r'">([^<]+)<', ft_raw_html)
                fields["ft_name"] = text_m.group(1).strip() if text_m else None

    # Strip HTML tags and entities from all string fields
    for k, v in list(fields.items()):
        if isinstance(v, str) and k not in ("format", "ft_link"):
            fields[k] = _strip_compact_html(v) or None

    # Gravity raw: everything before the BÉLANGER block
    before = _strip_compact_html(description[:m_start.start()])
    fields["gravity_raw"] = before or None

    return fields


# ── Gravity Forms raw-dump parser ─────────────────────────────────────────────

# Markers for untriaged Gravity Forms submissions (flat "Label : Value" blocks).
_GF_MARKER = re.compile(
    r"^(?:Date et heure de l.appel|Num[eé]ro unique d.unit[eé]|Nom complet de l.appelant)",
    re.MULTILINE | re.IGNORECASE,
)

# French label → output field name. Only fields we actually extract.
_GF_LABEL_MAP: dict[str, str] = {
    "date et heure de l appel":             "submission_date",
    "type de l appelant":                    "caller_type",
    "numero unique d unite":                 "unit_number",
    "nom complet de l appelant":             "caller_name",
    "telephone de l appelant":               "caller_phone",
    "courriel de l appelant":                "caller_email",
    "urgent ou non-urgent":                  "urgency_raw",
    "categorie":                             "category_raw",
    "adresse de l urgence":                  "address_urgency",
    "details, commentaires ou autre":        "message",
    "acces au logement":                     "entry_permission",
    "avez-vous des animaux?":                "animals",
    "avez-vous des animaux":                 "animals",
    "j ai avise des frais, si applicable":   "fees_advised",
    "j ai avise des frais si applicable":    "fees_advised",
}


def _gf_nrm_label(label: str) -> str:
    """Normalize a Gravity Forms label for lookup: lowercase, strip accents and apostrophes, collapse whitespace."""
    s = unicodedata.normalize("NFD", label.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"['’ʼ]", " ", s)  # apostrophes survive Mn filter — strip explicitly
    return re.sub(r"\s+", " ", s).strip()


def _parse_gravity_forms(description: str) -> dict:
    """Parse an untriaged Gravity Forms submission (flat Label : Value block)."""
    text = html.unescape(description)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace(" ", "\n")   # LINE SEPARATOR used in telephony notifications
    text = _HTML_TAG_RE.sub("", text)

    fields: dict[str, Any] = {
        "format":          "gravity_forms",
        "submission_date": None,
        "caller_type":     None,
        "unit_number":     None,    # official unit ID per SKILL.md — valuable even pre-triage
        "caller_name":     None,
        "caller_phone":    None,
        "caller_email":    None,
        "urgency_raw":     None,
        "category_raw":    None,
        "address_urgency": None,
        "entry_permission":None,
        "animals":         None,
        "message":         None,
        "fees_advised":    None,
        "gravity_raw":     None,
    }

    # Locate start of the form block; everything before it is technician follow-up notes.
    m_start = _GF_MARKER.search(text)
    if not m_start:
        return fields

    pre_text = text[:m_start.start()].strip()
    fields["gravity_raw"] = pre_text or None

    form_text = text[m_start.start():]

    # Label-anchored splitter: within each blank-line paragraph, scan line-by-line.
    # A line whose text before ':' normalises to a known GF label opens a new field.
    # Any other non-empty line is appended to the current field's value.
    # Blank lines delimit paragraphs, preventing guard-contact blocks from contaminating
    # the last GF field. Events that use single-\n separators (no blank lines) are
    # handled because all lines land in one paragraph and the label check still fires.
    for para in re.split(r"\n\s*\n", form_text):
        para = para.strip()
        if not para:
            continue
        current_key: str | None = None
        current_val: list[str] = []
        for line in para.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(.+?)\s*:\s*(.*)", line)
            if m:
                key = _GF_LABEL_MAP.get(_gf_nrm_label(m.group(1).strip()))
                if key:
                    if current_key and current_val:
                        fields[current_key] = "\n".join(current_val)
                    current_key = key
                    current_val = [m.group(2).strip()] if m.group(2).strip() else []
                    continue
            if current_key:
                current_val.append(line)
        if current_key and current_val:
            fields[current_key] = "\n".join(current_val)

    return fields


# ── Building cross-reference ──────────────────────────────────────────────────


def _nrm(s: str) -> str:
    """Lowercase + strip accents + replace hyphens with spaces for fuzzy matching."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("-", " ").strip()


# Build lookup indexes
_TF_BY_NAME: dict[str, dict] = {}      # original lowercase name → row
_TF_BY_NAME_NRM: dict[str, dict] = {}  # normalized name → row (for accent-insensitive match)
_TF_BY_PROJECT: dict[str, list[dict]] = {}
# "N a M" range entries: (low, high, street_words_nrm, row)
_TF_RANGE_INDEX: list[tuple[int, int, list[str], dict]] = []

_RANGE_A_BN_RE = re.compile(r"^(\d+)\s+a\s+(\d+)\s+(.*)", re.IGNORECASE)

for _row in TABLE_FONDAMENTALE:
    _bn_orig = (_row.get("unique_building_name") or "").strip()
    _bn = _bn_orig.lower()
    if _bn:
        _TF_BY_NAME[_bn] = _row
        _m = _RANGE_A_BN_RE.match(_bn_orig)
        if _m:
            _low, _high = int(_m.group(1)), int(_m.group(2))
            _sw = [w for w in _nrm(_m.group(3)).split() if len(w) >= 3]
            _TF_RANGE_INDEX.append((_low, _high, _sw, _row))
            # Range entries are matched exclusively via _TF_RANGE_INDEX (step 1).
            # Omit from _TF_BY_NAME_NRM to prevent substring false-positives in step 2,
            # e.g. civic=40 matching "940 a 952 Wilfrid-Pelletier" via "40" ⊂ "940...".
        else:
            _TF_BY_NAME_NRM[_nrm(_bn)] = _row
    _pn = (_row.get("unique_project_name") or "").lower().strip()
    if _pn:
        _TF_BY_PROJECT.setdefault(_pn, []).append(_row)


def _match_building(street: str | None, civic: str | None, project: str | None) -> dict | None:
    """Try to find a Table Fondamentale row for this event. Returns row or None."""
    if project:
        key = project.lower().strip()
        rows = _TF_BY_PROJECT.get(key)
        if rows and len(rows) == 1:
            return rows[0]
        if rows:
            if civic:
                # Range check first (avoids "4" matching "62-84" via substring)
                try:
                    civic_int = int(civic)
                    for r in rows:
                        bn = r.get("unique_building_name", "")
                        m = _RANGE_A_BN_RE.match(bn)
                        if m and int(m.group(1)) <= civic_int <= int(m.group(2)):
                            return r
                except ValueError:
                    pass
                # Token match: civic must appear as a word, not a substring
                for r in rows:
                    bn_n = _nrm(r.get("unique_building_name", ""))
                    if civic in bn_n.split():
                        return r
            return rows[0]  # ambiguous — return first, flag later

    if street and civic:
        street_words = [w for w in _nrm(street).split() if len(w) >= 3]

        # 1. Numeric range check for "N a M" entries (e.g. "940 a 952 Wilfrid-Pelletier").
        #    Substring matching fails for intermediary civics (944 ∉ "940 a 952 wilfrid...").
        try:
            civic_int = int(civic)
            for low, high, tf_sw, row in _TF_RANGE_INDEX:
                if low <= civic_int <= high and any(
                    # prefix match handles singular/plural (e.g. "chatelet" ↔ "chatelets")
                    tf_w.startswith(sw) or sw.startswith(tf_w)
                    for sw in street_words
                    for tf_w in tf_sw
                ):
                    return row
        except ValueError:
            pass

        # 2. Normalized substring/token match (handles single-civic and "N-M-P" multi entries;
        #    the civic IS a substring of e.g. "636 640 646 st jean" so this covers both).
        civic_n = civic.lower().strip()
        for name_n, row in _TF_BY_NAME_NRM.items():
            if civic_n in name_n and any(w in name_n for w in street_words):
                return row

    return None


# ── Provenance helpers ────────────────────────────────────────────────────────

def _prov(event: dict, cal_id: str, col: str, raw, ingested):
    log_provenance(
        target_table="maintenance_request",
        target_pk=None,  # no PK until write-back
        target_column=col,
        source_type="google_calendar",
        source_drive_id=cal_id,
        source_file_name=None,
        source_tab=None,
        source_row=event.get("htmlLink"),
        source_column=col,
        raw_value=raw,
        ingested_value=ingested,
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(dry_run: bool = True, silent: bool = False,
        start_dt: datetime | None = None, end_dt: datetime | None = None) -> list[dict]:
    creds   = _get_creds()
    service = build("calendar", "v3", credentials=creds)

    if start_dt is None or end_dt is None:
        # 45-day rolling window
        today    = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt   = today  # exclusive — events up to end of yesterday
        start_dt = end_dt - timedelta(days=45)
        window_desc = "45 days"
    else:
        window_desc = f"{(end_dt - start_dt).days} days"

    print(f"\nWindow: {start_dt.date()} → {(end_dt - timedelta(days=1)).date()} ({window_desc}, end exclusive={end_dt.date()})")

    all_raw: list[tuple[str, str, dict]] = []  # (cal_key, cal_id, event)
    counts_raw: dict[str, int] = {}

    for cal_key, cal_id in CALENDAR_IDS.items():
        events = _pull_events(service, cal_id, start_dt, end_dt)
        counts_raw[cal_key] = len(events)
        for ev in events:
            all_raw.append((cal_key, cal_id, ev))

    print(f"Raw events pulled: main={counts_raw['main']}, st_maj={counts_raw['st_maj']}, total={len(all_raw)}")

    # Exclusion pass
    kept: list[tuple[str, str, dict]] = []
    exclusion_counts: dict[str, int] = {}
    for cal_key, cal_id, ev in all_raw:
        excluded, reason = _is_excluded(ev)
        if excluded:
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
        else:
            kept.append((cal_key, cal_id, ev))

    print(f"After exclusions: {len(kept)} events kept")
    print("Exclusion breakdown:")
    for reason, n in sorted(exclusion_counts.items(), key=lambda x: -x[1]):
        print(f"  {reason:<35s}: {n}")

    # Parse each event
    results: list[dict] = []
    unknown_codes: dict[str, int] = {}
    unmatched_buildings: list[dict] = []
    format_counts = {"v10": 0, "v10_plaintext": 0, "v10_legacy": 0, "gravity_forms": 0, "belanger_compact": 0, "unparsed_body_format": 0}

    for cal_key, cal_id, ev in kept:
        title = ev.get("summary", "")
        desc  = ev.get("description", "") or ""
        link  = ev.get("htmlLink", "")
        event_id = ev.get("id", "")
        color = ev.get("colorId")
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date", "")

        # Title parse
        title_fields = _parse_title(title)

        # Log unknown employee codes
        code = title_fields.get("employee_code")
        if code and not title_fields.get("employee_known"):
            norm = code.replace("-", "")
            if norm not in KNOWN_EMPLOYEE_CODES:
                unknown_codes[code] = unknown_codes.get(code, 0) + 1

        # Body format detection (order matters)
        desc_plain = html.unescape(desc)
        if _V10_MARKER.search(desc):
            body_fields = _parse_v10(desc)
            fmt = "v10"
        elif _V10_PLAIN_MARKER.search(desc):
            body_fields = _parse_v10_plaintext(desc)
            fmt = "v10_plaintext"
        elif _V10_LEGACY_MARKER.search(desc):
            body_fields = _parse_v10_legacy(desc)
            fmt = "v10_legacy"
        elif _GF_MARKER.search(desc_plain):
            body_fields = _parse_gravity_forms(desc)
            fmt = "gravity_forms"
        elif _BEL_START.search(desc_plain):
            body_fields = _parse_belanger_compact(desc_plain)
            fmt = "belanger_compact"
        else:
            body_fields = {
                "format":       "unparsed_body_format",
                "gravity_raw":  desc.strip() or None,
            }
            fmt = "unparsed_body_format"

        format_counts[fmt] = format_counts.get(fmt, 0) + 1

        # Building cross-reference
        project   = body_fields.get("projet") or title_fields.get("street")
        street    = title_fields.get("street")
        civic     = title_fields.get("civic")
        tf_row    = _match_building(street, civic, project)

        if tf_row is None:
            unmatched_buildings.append({
                "calendar_key": cal_key,
                "event_id":     event_id,
                "title":        title,
                "street":       street,
                "civic":        civic,
                "project":      project,
                "link":         link,
            })

        # Assemble result
        record = {
            "calendar_key":     cal_key,
            "calendar_id":      cal_id,
            "event_id":         event_id,
            "html_link":        link,
            "start":            start,
            "raw_title":        title,
            "body_format":      fmt,
            "tf_match":         tf_row.get("unique_building_name") if tf_row else None,
            **title_fields,
            **body_fields,
        }
        results.append(record)

        # Provenance for key fields (title-derived)
        if not dry_run:
            _prov(ev, cal_id, "title",          title, title)
            _prov(ev, cal_id, "employee_code",  title, title_fields["employee_code"])
            _prov(ev, cal_id, "urgency",        title, title_fields["urgency"])
            _prov(ev, cal_id, "problem_summary",title, title_fields["problem_summary"])
            for col in ("problems", "occupants_raw", "bail_raw", "unite", "projet",
                        "ft_link", "doublons", "synergie_raw", "autres_notes"):
                val = body_fields.get(col)
                if val is not None:
                    _prov(ev, cal_id, col, val, val)

    if dry_run and not silent:
        _print_report(results, format_counts, unknown_codes, unmatched_buildings, kept)

    return results


# ── Dry run report ────────────────────────────────────────────────────────────

def _print_report(results, format_counts, unknown_codes, unmatched_buildings, kept):
    total = len(results)
    print(f"\n{'='*70}")
    print(f"DRY RUN — parse_calendar_requests.py")
    print(f"{'='*70}")
    print(f"\nEvents after filtering: {total}")
    print("\n── Format breakdown ──")
    for fmt, n in sorted(format_counts.items(), key=lambda x: -x[1]):
        pct = f"{100*n/total:.0f}%" if total else "n/a"
        print(f"  {fmt:<30s}: {n:>4}  ({pct})")

    print(f"\n── Unknown employee codes ──")
    if unknown_codes:
        for code, n in sorted(unknown_codes.items(), key=lambda x: -x[1]):
            print(f"  {code:<8}: {n} events")
    else:
        print("  (none)")

    print(f"\n── Unmatched buildings (no Table Fondamentale hit): {len(unmatched_buildings)} ──")
    for b in unmatched_buildings[:20]:
        print(f"  [{b['calendar_key']}] {b['title']!r}")
        if b['civic'] or b['street']:
            print(f"            civic={b['civic']!r}  street={b['street']!r}  project={b['project']!r}")

    # Sample events: pick up to 5, prioritising one of each format
    print(f"\n{'='*70}")
    print(f"SAMPLE EVENTS (up to 5, one per format if possible)")
    print(f"{'='*70}")

    seen_formats: set[str] = set()
    samples: list[dict] = []
    for r in results:
        if r["body_format"] not in seen_formats:
            seen_formats.add(r["body_format"])
            samples.append(r)
        if len(samples) >= 5:
            break
    # Fill remaining slots from first results
    for r in results:
        if len(samples) >= 5:
            break
        if r not in samples:
            samples.append(r)

    # Translate prose fields in a copy of each sample before printing.
    # This is the only place translation runs in dry-run mode (avoids translating all 1200+ events).
    print("(translating sample events...)", flush=True)
    for s in samples:
        s_copy = dict(s)
        _translate_prose_fields(s_copy)
        _print_sample(s_copy)


def _print_sample(s: dict):
    print(f"\n── {s['calendar_key']} | {s['start'][:10] if s['start'] else '?'} | format={s['body_format']} ──")
    print(f"   TITLE        : {s['raw_title']!r}")
    print(f"   event_id     : {s['event_id']}")
    print(f"   link         : {s['html_link']}")
    print(f"   employee_code: {s['employee_code']!r}  known={s['employee_known']}")
    print(f"   urgency      : {s['urgency']!r}")
    print(f"   civic        : {s['civic']!r}")
    print(f"   unit         : {s['unit']!r}")
    print(f"   street       : {s['street']!r}")
    print(f"   problem      : {s['problem_summary']!r}")
    print(f"   tf_match     : {s['tf_match']!r}")

    # Body fields — shown post-translation (prose fields already translated by caller)
    body_keys = [
        "problems", "entry_permission", "animals", "occupants_raw", "bail_raw",
        "ft_link", "ft_name", "historique_raw", "tri", "delegable", "report",
        "doublons", "synergie_raw", "unite", "projet", "temps", "complexite",
        "sous_traitant", "assignation", "autres_notes", "embourbement",
        # gravity_forms fields
        "submission_date", "caller_type", "unit_number", "caller_name",
        "caller_phone", "caller_email", "urgency_raw", "message",
        # compact / shared fields
        "building_raw", "heating_raw", "signed_date",
    ]
    for key in body_keys:
        val = s.get(key)
        if val is not None:
            val_str = str(val)
            if len(val_str) > 120:
                val_str = val_str[:117] + "..."
            print(f"   {key:<20s}: {val_str!r}")

    # Provenance stub (dry run — actual rows not flushed)
    print(f"   [provenance]  : source_type=google_calendar, source_row={s['html_link']!r}")


if __name__ == "__main__":
    run(dry_run=True)
