"""
Per-request context builder for the AI triage service.

One function per context block, each independently testable.
All time windows anchored on request.start_date (guide §4.1) — never now().
No model involvement; pure SQL → dicts.

Occupant inference assumption (guide rule 21 / RRIA substitution)
------------------------------------------------------------------
tenancy_record.start_date and tenancy_record.end_date are NULL on all
MRR-backfilled rows (5,558 of 5,616 total). "Current occupants as of
request.start_date" is therefore derived from lease.debut_bail and
lease.fin_bail rather than actual tenancy start/end dates.

Consequence: a unit where the lease continued through a cession, a
roommate addition, or a partial changeover will show WHOEVER IS ON THE
CURRENT LEASE, which may not match who actually lives there today.
This is acceptable for triage — coordinators need a name and phone to
call, and the lease tenant is the right starting point.

The 52 tenancy_record rows that DO have real start dates (arrivals from
the unit_turnover backfill) and 6 with real end dates (departures) are
not preferred over the lease-derived path. Mixing them would create a
two-track system where 1% of queries use actual tenancy dates and 99%
use lease approximations. The inconsistency is worse than the uniformity;
the lease path is kept for all rows.

Synergy scope narrowing
-----------------------
synergy() returns a dict, not a list, because the scope of the result
matters: {scope, items, total, narrowed_from}. scope is one of:
  'project'   — all candidates within the project fit under the threshold
  'building'  — project scope exceeded threshold; result is building-scoped
  'saturated' — building scope also exceeds threshold; items is empty,
                total gives the building-scope count so the model knows
                the inventory is large, not that no synergy exists
Never truncated silently.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, timedelta, datetime
from typing import Any

import psycopg2.extras


def _ref_date(request: dict) -> date | None:
    """Return start_date, or submission_date.date() when start_date is NULL (intake rows)."""
    d = request.get("start_date")
    if d is not None:
        return d
    sub = request.get("submission_date")
    if sub is None:
        return None
    if isinstance(sub, datetime):
        return sub.date()
    if isinstance(sub, date):
        return sub
    return None


# ── Pest-control keyword detection ────────────────────────────────────────────
# Used to determine stream for synergy scoping when request is not yet triaged.

_PEST_RE = re.compile(
    r"extermin|coquerelle|punais|fourmi|gu[eê]pe|abeille|rongeur|"
    r"insecte|cafard|mille.patte|araign[eé]e|vermine|souris|rat\b",
    re.IGNORECASE,
)


# ── Mechanical exclusions (guide §4.2 / SKILL 4.2) ────────────────────────────
# Recurring series, waste-ish admin lists, `!` admin prefix. Applied in SQL
# candidate queries AND as a Python gate so the model cannot cite them.

# Each tuple = all substrings that must appear (case-insensitive) in raw_title.
_EXCL_TOKEN_GROUPS: tuple[tuple[str, ...], ...] = (
    ("abri", "hiver"),
    ("tapis", "hiver"),
    ("lavage", "vitre"),
    ("inspection", "incendie"),
    ("liste choses à faire",),
    ("compresseur",),
    ("batterie",),
)


def is_mechanically_excluded(title: str | None) -> bool:
    """True when raw_title matches SKILL §4.2 mechanical exclusions."""
    t = title or ""
    if t.startswith("!"):
        return True
    low = t.casefold()
    for group in _EXCL_TOKEN_GROUPS:
        if all(tok.casefold() in low for tok in group):
            return True
    return False


def _excl_sql() -> str:
    """SQL AND-clause mirroring is_mechanically_excluded (candidate filters)."""
    parts = ["mr.raw_title NOT LIKE '!%%'"]
    for group in _EXCL_TOKEN_GROUPS:
        if len(group) == 1:
            parts.append(f"mr.raw_title NOT ILIKE '%%{group[0]}%%'")
        else:
            # Same token-order as historical ILIKE '%%a%%b%%' patterns.
            parts.append(
                "mr.raw_title NOT ILIKE '%%" + "%%".join(group) + "%%'"
            )
    return "\n    AND " + "\n    AND ".join(parts)


_EXCL = _excl_sql()

# Candidate columns returned for duplicate / synergy / history blocks.
_CAND_COLS = """
    mr.request_id,
    mr.raw_title,
    mr.start_date,
    mr.problem_summary,
    mr.problems,
    mr.status,
    mr.complexity_tier,
    mr.congestion_level,
    mr.triage_summary,
    mr.subcontractor_name,
    mr.routing_rule,
    mr.duplicate_of_request_id,
    mr.addition_to_request_id,
    mr.source_calendar
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _as_dict(cur, row) -> dict:
    if isinstance(row, dict):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur) -> list[dict]:
    return [_as_dict(cur, row) for row in cur.fetchall()]


def _one(cur) -> dict | None:
    row = cur.fetchone()
    return _as_dict(cur, row) if row else None


def _is_pest(request: dict) -> bool:
    for field in ("problems", "problem_summary", "triage_summary", "animals"):
        if _PEST_RE.search(request.get(field) or ""):
            return True
    return False


def _stream(request: dict) -> str:
    """Return 'pest', 'subcontractor', or 'internal'."""
    sub = request.get("subcontractor_name") or ""
    if _PEST_RE.search(sub):
        return "pest"
    if request.get("vendor_id") or sub.lower().startswith("oui"):
        return "subcontractor"
    if _is_pest(request):
        return "pest"
    return "internal"


# ── Block 1: unit context ─────────────────────────────────────────────────────

def unit_context(cur, request: dict) -> dict | None:
    """
    Current unit + lease + all occupants as of request.start_date.
    Returns None when no active lease is found (blocking per guide rule 21).

    Occupant list is derived from lease.debut_bail/fin_bail, not from
    tenancy_record.start_date/end_date (NULL on all backfilled rows).
    See module docstring for the full assumption and its limits.
    """
    d = _ref_date(request)
    unit_id = request["unit_id"]

    cur.execute(
        """
        SELECT
            u.unit_id, u.rue, u.numero_appartement, u.grandeur,
            l.lease_id, l.debut_bail, l.fin_bail,
            l.langue_bail, l.droit_animaux, l.statut
        FROM unit u
        JOIN lease l ON l.unit_id = u.unit_id
        WHERE u.unit_id = %s
          AND (l.debut_bail IS NULL OR l.debut_bail <= %s)
          AND (l.fin_bail IS NULL OR l.fin_bail >= %s)
        ORDER BY l.debut_bail DESC NULLS LAST
        LIMIT 1
        """,
        (unit_id, d, d),
    )
    row = _one(cur)
    if row is None:
        return None

    # Occupants — filter through lease dates, not tenancy_record.start/end_date
    # (backfilled records have NULL start/end_date; lease dates are authoritative).
    cur.execute(
        """
        SELECT
            t.tenant_id,
            t.nom_complet,
            t.telephone,
            t.telephone_international,
            t.courriel,
            tr.capacite
        FROM tenancy_record tr
        JOIN lease l ON tr.lease_id = l.lease_id
        JOIN tenant t ON tr.tenant_id = t.tenant_id
        WHERE l.unit_id = %s
          AND (l.debut_bail IS NULL OR l.debut_bail <= %s)
          AND (l.fin_bail IS NULL OR l.fin_bail >= %s)
        ORDER BY tr.capacite, t.nom_complet
        """,
        (unit_id, d, d),
    )
    row["occupants"] = _rows(cur)
    return row


def _plus_months(d: date, months: int) -> date:
    m0 = d.month - 1 + months
    year = d.year + m0 // 12
    month = m0 % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


_EN_LANG = re.compile(r"anglais|english|\ben\b", re.IGNORECASE)
_YES_PET = re.compile(r"oui|yes|chien|chat|animal|dog|cat|oiseau|poisson")


def _declared_pets(animals: str | None) -> bool | None:
    folded = _fold(animals or "")
    if not folded:
        return None
    if _YES_PET.search(folded):
        return True
    if folded.startswith("non") or folded.startswith("no") or "aucun" in folded or folded in {"sans", "none"}:
        return False
    return True


def _caller_on_lease(request: dict, occupants: list[dict]) -> bool | None:
    """None when there is nothing to compare. False when the caller is not a lease holder."""
    caller_id = request.get("caller_tenant_id")
    tokens = [t for t in _fold(request.get("caller_name") or "").split() if len(t) >= 3]
    if not tokens and not caller_id:
        return None
    if not occupants:
        return None
    if caller_id and any(o.get("tenant_id") == caller_id for o in occupants):
        return True
    if not tokens:
        return False
    for occ in occupants:
        words = set(_fold(occ.get("nom_complet") or "").split())
        if len(tokens) >= 2 and all(t in words for t in tokens):
            return True
        if len(tokens) == 1 and tokens[0] in words:
            return True
    return False


def rentroll_checks(request: dict, unit: dict | None) -> dict:
    """
    RRIA facts the note must carry (guide rule 21 / v10.5).
    Appliances and furniture are omitted: those tables are not used in triage.
    A housing unit with no active lease is a blocker (lease_missing).
    """
    if not request.get("unit_id"):
        return {
            "applies": False,
            "lease_missing": False,
            "vacant": False,
            "langue_en": False,
            "recent_move_in": False,
            "pet_mismatch": False,
            "caller_mismatch": False,
            "required_notes": [],
        }
    if unit is None:
        return {
            "applies": True,
            "lease_missing": True,
            "vacant": False,
            "langue_en": False,
            "recent_move_in": False,
            "pet_mismatch": False,
            "caller_mismatch": False,
            "required_notes": [],
        }

    debut = unit.get("debut_bail")
    if isinstance(debut, datetime):
        debut = debut.date()
    ref = _ref_date(request)
    recent = (
        isinstance(debut, date)
        and isinstance(ref, date)
        and debut <= ref < _plus_months(debut, 3)
    )
    langue_en = bool(_EN_LANG.search(unit.get("langue_bail") or ""))
    pets = _declared_pets(request.get("animals"))
    pet_mismatch = pets is True and unit.get("droit_animaux") is not True
    occupants = unit.get("occupants") or []
    on_lease = _caller_on_lease(request, occupants)
    notes: list[str] = []
    if pet_mismatch:
        notes.append("ÉCART ANIMAUX")
    if on_lease is False:
        notes.append("RÉQUÉRANT ABSENT")
    if recent:
        notes.append("emménagement récent")
    if langue_en:
        notes.append("bail anglais")
    if not occupants:
        notes.append("LOGEMENT VACANT")
    return {
        "applies": True,
        "lease_missing": False,
        "vacant": not occupants,
        "langue_en": langue_en,
        "recent_move_in": recent,
        "pet_mismatch": pet_mismatch,
        "caller_mismatch": on_lease is False,
        "required_notes": notes,
    }


# ── Block 2: building context ─────────────────────────────────────────────────

def building_context(cur, request: dict) -> dict | None:
    """Building → project → sector, plus raw technical sheet."""
    cur.execute(
        """
        SELECT
            b.building_id, b.adresse, b.ville, b.code_postal,
            b.nb_logements, b.nb_etages, b.ascenseur, b.piscine,
            b.sauna, b.gym, b.chauffage, b.systeme_incendie,
            b.raw_fiche_technique,
            p.project_id, p.nom_unique_projet, p.accounting_project_number,
            s.territoire, s.color_code
        FROM building b
        JOIN project p ON b.project_id = p.project_id
        JOIN sector s ON b.sector_id = s.sector_id
        WHERE b.building_id = %s
        """,
        (request["building_id"],),
    )
    return _one(cur)


# ── Same-problem vs different-problem (guide rule 12) ─────────────────────────

_STOPWORDS = frozenset({
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a", "au", "aux",
    "en", "pour", "dans", "sur", "avec", "sans", "qui", "que", "ce", "cette", "pas",
    "ne", "est", "sont", "the", "an", "of", "and", "or", "to", "in", "on", "for",
    "with", "from", "is", "are", "at", "par", "plus", "tres", "très", "aussi",
})
_STRIP_URGENCY = re.compile(r"^(AJD|ajd)\s+")
_DOUBLON_MARK = re.compile(r"DOUBLON\s+POTENTIEL", re.IGNORECASE)


def problem_text(row: dict) -> str:
    """Concatenate title + problem fields for sameness comparison."""
    parts = [
        row.get("raw_title") or row.get("title") or "",
        row.get("problems") or "",
        row.get("problem_summary") or "",
    ]
    if isinstance(parts[1], list):
        parts[1] = " ".join(str(p) for p in parts[1])
    return " ".join(parts)


def problem_tokens(text: str) -> frozenset[str]:
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = _STRIP_URGENCY.sub("", t)
    t = _DOUBLON_MARK.sub(" ", t)
    # Prefer the summary after the unit/address colon when present.
    if ":" in t:
        t = t.rsplit(":", 1)[-1]
    return frozenset(
        tok for tok in re.findall(r"[a-z0-9]{3,}", t) if tok not in _STOPWORDS
    )


def same_problem(a: str, b: str) -> bool:
    """True when two problem texts look like the same issue (guide rule 12)."""
    ta, tb = problem_tokens(a), problem_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    if inter == 0:
        return False
    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))
    return jaccard >= 0.35 or containment >= 0.6


# ── Block 3: duplicates ───────────────────────────────────────────────────────

def duplicates(cur, request: dict) -> list[dict]:
    """
    Same unit_id, open calls only, window −90d → +45d from request.start_date.
    Each row gets problem_relation = same_problem | different_problem.
    """
    d = _ref_date(request)
    unit_id = request.get("unit_id")
    if d is None or unit_id is None:
        return []
    cur.execute(
        f"""
        SELECT {_CAND_COLS}
        FROM maintenance_request mr
        WHERE mr.unit_id = %s
          AND mr.request_id != %s
          AND mr.status::text <> 'closed'
          AND mr.start_date BETWEEN (%s - INTERVAL '90 days') AND (%s + INTERVAL '45 days')
          {_EXCL}
        ORDER BY mr.start_date DESC
        """,
        (unit_id, request["request_id"], d, d),
    )
    src = problem_text(request)
    out = []
    for r in _rows(cur):
        r["problem_relation"] = (
            "same_problem" if same_problem(src, problem_text(r)) else "different_problem"
        )
        out.append(r)
    return out


# ── Block 4: synergy ──────────────────────────────────────────────────────────

# Guide "2 pages" heuristic applied to LLM context: 100 candidates ≈ 25–30K
# tokens for synergy alone, leaving ample room in the 200K window.
_SYNERGY_THRESHOLD = 100
# Skill §8: at most 5 clickable synergy lines; the rest stay compact.
_SYNERGY_LINK_CAP = 5
# Internal stream excludes portfolio-wide specialists (skill: Duclos, Body Gym,
# Éric, 4 Saisons, Électro DB, Fortin, Newtech). Pest stream still sees Éric.
_EXCLUSIVE_VENDOR_SQL = r"""
    AND (
        mr.subcontractor_name IS NULL
        OR mr.subcontractor_name !~* 'duclos|body[[:space:]]*gym|[eé]ric|4[[:space:]]*saisons|[eé]lectro[[:space:]]*db|fortin|newtech'
    )
"""


def _mark_saturday(rows: list[dict]) -> list[dict]:
    """Saturday landing is not a real shared visit date (guide rule 18)."""
    for r in rows:
        sd = r.get("start_date")
        r["saturday_landing"] = bool(sd is not None and sd.weekday() == 5)
    return rows


def _synergy_result(scope: str, rows: list[dict], *, total: int | None = None, narrowed_from, extra: dict | None = None) -> dict:
    marked = _mark_saturday(rows)
    out = {
        "scope": scope,
        "items": marked,
        "total": len(marked) if total is None else total,
        "narrowed_from": narrowed_from,
        "link_cap": _SYNERGY_LINK_CAP,
    }
    if extra:
        out.update(extra)
    return out


def synergy(cur, request: dict) -> dict:
    """
    Same project_id, −60d → +21d, stream-scoped per guide rule 13.

    Returns dict: {scope, items, total, narrowed_from}
      scope='project'   — items is the exhaustive project-scope list
      scope='building'  — project exceeded threshold; items is building-scoped
      scope='saturated' — building also exceeds threshold; items is []; total
                          is the building-scope count so the model knows the
                          stream is large, not absent
    Never truncates silently. See module docstring for the full policy.
    """
    if not request.get("project_id"):
        return _synergy_result("project", [], narrowed_from=None)

    d = _ref_date(request)
    if d is None:
        return _synergy_result("project", [], narrowed_from=None)
    stream = _stream(request)

    if stream == "pest":
        return _synergy_pest(cur, request, d)

    # Build the stream-specific WHERE fragment and extra params
    if stream == "internal":
        stream_where = """
            AND (mr.vendor_id IS NULL)
            AND (mr.subcontractor_name IS NULL OR mr.subcontractor_name NOT ILIKE 'Oui%%')
        """ + _EXCLUSIVE_VENDOR_SQL
        extra_params: tuple = ()
    else:
        vid = request.get("vendor_id")
        sub = (request.get("subcontractor_name") or "").strip()
        if vid:
            stream_where = "AND mr.vendor_id = %s"
            extra_params = (vid,)
        elif sub:
            sub_prefix = re.split(r"[;(]", sub)[0].strip()
            stream_where = "AND mr.subcontractor_name ILIKE %s"
            extra_params = (f"{sub_prefix}%",)
        else:
            return _synergy_result("project", [], narrowed_from=None)

    window = "AND mr.start_date BETWEEN (%s - INTERVAL '60 days') AND (%s + INTERVAL '21 days')"

    # 1. Project scope — exhaustive within stream
    cur.execute(
        f"""
        SELECT {_CAND_COLS}
        FROM maintenance_request mr
        WHERE mr.project_id = %s
          AND mr.request_id != %s
          {window}
          {_EXCL}
          {stream_where}
        ORDER BY mr.start_date DESC
        """,
        (request["project_id"], request["request_id"], d, d) + extra_params,
    )
    proj_rows = _rows(cur)

    if len(proj_rows) <= _SYNERGY_THRESHOLD:
        return _synergy_result("project", proj_rows, narrowed_from=None)

    # 2. Narrow to building scope (guide §4.1: "if the key is too broad, narrow it")
    cur.execute(
        f"""
        SELECT {_CAND_COLS}
        FROM maintenance_request mr
        WHERE mr.building_id = %s
          AND mr.request_id != %s
          {window}
          {_EXCL}
          {stream_where}
        ORDER BY mr.start_date DESC
        """,
        (request["building_id"], request["request_id"], d, d) + extra_params,
    )
    bldg_rows = _rows(cur)
    narrowed = f"project scope found {len(proj_rows)} candidates (threshold {_SYNERGY_THRESHOLD}); narrowed to building"

    if len(bldg_rows) <= _SYNERGY_THRESHOLD:
        return _synergy_result("building", bldg_rows, narrowed_from=narrowed)

    # 3. Saturated — report count, no silent subset
    return _synergy_result("saturated", [], total=len(bldg_rows), narrowed_from=narrowed)


def _synergy_pest(cur, request: dict, d: date) -> dict:
    """
    Pest stream: building-first exhaustive list, then project remainder.
    Window open-ended forward (guide rule 13: optimise exterminator visit).
    Pest candidates identified by subcontractor_name keyword.
    """
    pest_filter = "AND mr.subcontractor_name ~* 'extermin|Éric.extermin'"

    cur.execute(
        f"""
        SELECT {_CAND_COLS}, 'building' AS pest_scope
        FROM maintenance_request mr
        WHERE mr.building_id = %s
          AND mr.request_id != %s
          AND mr.start_date >= (%s - INTERVAL '60 days')
          {_EXCL}
          {pest_filter}
        ORDER BY mr.start_date
        """,
        (request["building_id"], request["request_id"], d),
    )
    rows = _rows(cur)

    cur.execute(
        f"""
        SELECT {_CAND_COLS}, 'project' AS pest_scope
        FROM maintenance_request mr
        WHERE mr.project_id = %s
          AND mr.building_id != %s
          AND mr.request_id != %s
          AND mr.start_date >= (%s - INTERVAL '60 days')
          {_EXCL}
          {pest_filter}
        ORDER BY mr.start_date
        """,
        (request["project_id"], request["building_id"], request["request_id"], d),
    )
    rows += _rows(cur)

    cur.execute(
        """
        SELECT pc.case_id, pc.pest_type, pc.first_reported_date,
               pc.warranty_active, pc.warranty_expiry_date,
               vc.nom AS vendor_nom
        FROM pest_control_case pc
        LEFT JOIN vendor_contact vc ON pc.vendor_id = vc.vendor_id
        WHERE pc.building_id = %s AND pc.warranty_active = true
        """,
        (request["building_id"],),
    )
    warranty_cases = _rows(cur)

    return _synergy_result(
        "pest",
        rows,
        narrowed_from=None,
        extra={"warranty_cases": warranty_cases},
    )


# Open calls in the same sector → N1–N5. Cutoffs are ours until François
# publishes bands; the skill's frozen "État actuel : N5" is a snapshot, not a formula.
_CONGESTION_BANDS = ((15, "N1"), (40, "N2"), (80, "N3"), (150, "N4"))
_CONGESTION_LABELS = {
    "N1": "au-dessus de nos affaires",
    "N2": "niveau courant",
    "N3": "en retard",
    "N4": "très en retard",
    "N5": "critique",
}


def congestion_level_for_count(n: int) -> str:
    for cap, level in _CONGESTION_BANDS:
        if n <= cap:
            return level
    return "N5"


def congestion(cur, request: dict) -> dict:
    """Open (not closed) calls in this sector, excluding the request itself."""
    sector_id = request.get("sector_id")
    if sector_id is None:
        level = "N2"
        return {"level": level, "open_count": 0, "label": _CONGESTION_LABELS[level], "sector_id": None}
    cur.execute(
        """
        SELECT count(*) FROM maintenance_request
        WHERE sector_id = %s
          AND request_id != %s
          AND status::text <> 'closed'
        """,
        (sector_id, request["request_id"]),
    )
    row = cur.fetchone()
    n = row[0] if not isinstance(row, dict) else row["count"]
    level = congestion_level_for_count(int(n))
    return {
        "level": level,
        "open_count": int(n),
        "label": _CONGESTION_LABELS[level],
        "sector_id": sector_id,
    }


# Stated cap — the prompt always reports how many rows were left out.
_HISTORY_CAP = 40


def _history_query(cur, *, where: str, params: tuple) -> list[dict]:
    cur.execute(
        f"""
        SELECT {_CAND_COLS}
        FROM maintenance_request mr
        WHERE {where}
          AND mr.request_id != %s
          AND mr.start_date BETWEEN (%s - INTERVAL '6 months') AND (%s + INTERVAL '21 days')
          {_EXCL}
        ORDER BY mr.start_date DESC
        """,
        params,
    )
    return _rows(cur)


def history(cur, request: dict) -> dict:
    """Unit history −6mo → +21d, plus building-level history when building_id is set.

    Building rows exclude anything already listed under the unit. Caps are
    reported, never silent. (Guide synergy/history rules are building-aware.)
    """
    d = _ref_date(request)
    empty = {
        "unit": [], "building": [],
        "unit_omitted": 0, "building_omitted": 0,
        "scope": "none",
    }
    if d is None:
        return empty
    rid = request["request_id"]
    unit_rows: list[dict] = []
    if request.get("unit_id") is not None:
        unit_rows = _history_query(
            cur,
            where="mr.unit_id = %s",
            params=(request["unit_id"], rid, d, d),
        )
    building_rows: list[dict] = []
    if request.get("building_id") is not None:
        seen = {r["request_id"] for r in unit_rows}
        building_rows = [
            r for r in _history_query(
                cur,
                where="mr.building_id = %s",
                params=(request["building_id"], rid, d, d),
            )
            if r["request_id"] not in seen
        ]

    def _cap(rows: list[dict]) -> tuple[list[dict], int]:
        if len(rows) <= _HISTORY_CAP:
            return rows, 0
        return rows[:_HISTORY_CAP], len(rows) - _HISTORY_CAP

    unit_shown, unit_omitted = _cap(unit_rows)
    bldg_shown, bldg_omitted = _cap(building_rows)
    if request.get("unit_id") is None and request.get("building_id") is not None:
        scope = "building"
    elif request.get("unit_id") is not None and request.get("building_id") is not None:
        scope = "unit+building"
    elif request.get("unit_id") is not None:
        scope = "unit"
    else:
        scope = "none"
    return {
        "unit": unit_shown,
        "building": bldg_shown,
        "unit_omitted": unit_omitted,
        "building_omitted": bldg_omitted,
        "scope": scope,
    }


# ── Block 6: photos ───────────────────────────────────────────────────────────

def photos(cur, request: dict) -> list[dict]:
    """Attachments on this request (feature 3.1 direct capture; no Gmail lookup)."""
    cur.execute(
        """
        SELECT attachment_id, drive_file_id, file_type
        FROM maintenance_attachment
        WHERE request_id = %s
        """,
        (request["request_id"],),
    )
    return _rows(cur)


# ── Fetch request row ─────────────────────────────────────────────────────────

def get_request(cur, request_id: int) -> dict | None:
    cur.execute(
        """
        SELECT *
        FROM maintenance_request
        WHERE request_id = %s
        """,
        (request_id,),
    )
    return _one(cur)


# ── Assemble full context ─────────────────────────────────────────────────────

def assemble(conn, request_id: int) -> dict:
    """
    Build the complete per-request context dict for triage.
    Raises ValueError if request not found.
    Returns a dict with keys: request, unit, building, duplicates, synergy, history, photos.
    unit is None when no current lease resolves (blocking condition per guide rule 21).
    """
    with conn.cursor() as cur:
        req = get_request(cur, request_id)
        if req is None:
            raise ValueError(f"request_id {request_id} not found")

        unit = unit_context(cur, req)
        return {
            "request":    req,
            "unit":       unit,
            "rentroll":   rentroll_checks(req, unit),
            "building":   building_context(cur, req),
            "duplicates": duplicates(cur, req),
            "synergy":    synergy(cur, req),
            "history":     history(cur, req),
            "congestion":  congestion(cur, req),
            "photos":      photos(cur, req),
        }


# ── Self-check ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os, json
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

    from backend.core.db import get_legacy_conn
    conn = get_legacy_conn()

    # Task 5: 10 historical requests — mix of buildings, formats, verdicts
    test_ids = [
        100, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000,
    ]

    # Use actual IDs that exist
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT request_id FROM maintenance_request
            WHERE start_date IS NOT NULL AND unit_id IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 10
            """
        )
        test_ids = [r[0] for r in cur.fetchall()]

    print(f"Testing {len(test_ids)} requests: {test_ids}\n")

    for rid in test_ids:
        ctx = assemble(conn, rid)
        req = ctx["request"]
        unit_ok = ctx["unit"] is not None
        occ_count = len(ctx["unit"]["occupants"]) if unit_ok else 0
        dup_count = len(ctx["duplicates"])
        syn = ctx["synergy"]
        hist = ctx["history"]
        hist_count = len(hist.get("unit", [])) + len(hist.get("building", []))
        photo_count = len(ctx["photos"])

        syn_summary = f"{syn['scope']}({syn['total']})"
        if syn["scope"] == "building":
            syn_summary += " [narrowed]"
        elif syn["scope"] == "saturated":
            syn_summary += " [saturated — items empty]"

        raw = json.dumps(ctx, default=str)
        tok_est = len(raw) // 4

        stream = _stream(req)
        print(
            f"  request_id={rid} | date={req['start_date']} | stream={stream}"
            f"\n    unit_ok={unit_ok} (occupants={occ_count})"
            f"  dups={dup_count}  synergy={syn_summary}"
            f"  history={hist_count}  photos={photo_count}"
            f"  ~{tok_est:,} tokens"
        )
        if not unit_ok:
            print(f"    [WARN] No active lease found — would be BLOCKING for live triage")

    conn.close()
    print("\nSelf-check complete.")
