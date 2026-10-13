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

import re
from datetime import date, timedelta
from typing import Any

import psycopg2.extras


# ── Pest-control keyword detection ────────────────────────────────────────────
# Used to determine stream for synergy scoping when request is not yet triaged.

_PEST_RE = re.compile(
    r"extermin|coquerelle|punais|fourmi|gu[eê]pe|abeille|rongeur|"
    r"insecte|cafard|mille.patte|araign[eé]e|vermine|souris|rat\b",
    re.IGNORECASE,
)


# ── Mechanical exclusion clause (injected into every candidate query) ─────────
# Guide §4.2: recurring series, admin rows, building lists, the request itself.
# The request_id exclusion is added separately per caller.

_EXCL = """
    AND mr.raw_title NOT LIKE '!%%'
    AND mr.raw_title NOT ILIKE '%%abri%%hiver%%'
    AND mr.raw_title NOT ILIKE '%%tapis%%hiver%%'
    AND mr.raw_title NOT ILIKE '%%lavage%%vitre%%'
    AND mr.raw_title NOT ILIKE '%%inspection%%incendie%%'
    AND mr.raw_title NOT ILIKE '%%liste choses à faire%%'
"""

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
    mr.addition_to_request_id
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one(cur) -> dict | None:
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


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
    d = request["start_date"]
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


# ── Block 3: duplicates ───────────────────────────────────────────────────────

def duplicates(cur, request: dict) -> list[dict]:
    """
    Same unit_id, window −90d → +45d from request.start_date.
    Mechanical exclusions applied. Self excluded.
    """
    d = request["start_date"]
    cur.execute(
        f"""
        SELECT {_CAND_COLS}
        FROM maintenance_request mr
        WHERE mr.unit_id = %s
          AND mr.request_id != %s
          AND mr.start_date BETWEEN (%s - INTERVAL '90 days') AND (%s + INTERVAL '45 days')
          {_EXCL}
        ORDER BY mr.start_date DESC
        """,
        (request["unit_id"], request["request_id"], d, d),
    )
    return _rows(cur)


# ── Block 4: synergy ──────────────────────────────────────────────────────────

# Guide "2 pages" heuristic applied to LLM context: 100 candidates ≈ 25–30K
# tokens for synergy alone, leaving ample room in the 200K window.
_SYNERGY_THRESHOLD = 100


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
        return {"scope": "project", "items": [], "total": 0, "narrowed_from": None}

    d = request["start_date"]
    stream = _stream(request)

    if stream == "pest":
        return _synergy_pest(cur, request, d)

    # Build the stream-specific WHERE fragment and extra params
    if stream == "internal":
        stream_where = """
            AND (mr.vendor_id IS NULL)
            AND (mr.subcontractor_name IS NULL OR mr.subcontractor_name NOT ILIKE 'Oui%%')
        """
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
            return {"scope": "project", "items": [], "total": 0, "narrowed_from": None}

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
        return {"scope": "project", "items": proj_rows, "total": len(proj_rows), "narrowed_from": None}

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
        return {"scope": "building", "items": bldg_rows, "total": len(bldg_rows), "narrowed_from": narrowed}

    # 3. Saturated — report count, no silent subset
    return {"scope": "saturated", "items": [], "total": len(bldg_rows), "narrowed_from": narrowed}


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

    return {
        "scope": "pest",
        "items": rows,
        "total": len(rows),
        "narrowed_from": None,
        "warranty_cases": warranty_cases,
    }


# ── Block 5: history ──────────────────────────────────────────────────────────

def history(cur, request: dict) -> list[dict]:
    """Same unit_id, −6mo → +21d. Excludes self and recurring events."""
    d = request["start_date"]
    cur.execute(
        f"""
        SELECT {_CAND_COLS}
        FROM maintenance_request mr
        WHERE mr.unit_id = %s
          AND mr.request_id != %s
          AND mr.start_date BETWEEN (%s - INTERVAL '6 months') AND (%s + INTERVAL '21 days')
          {_EXCL}
        ORDER BY mr.start_date DESC
        """,
        (request["unit_id"], request["request_id"], d, d),
    )
    return _rows(cur)


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

        return {
            "request":    req,
            "unit":       unit_context(cur, req),
            "building":   building_context(cur, req),
            "duplicates": duplicates(cur, req),
            "synergy":    synergy(cur, req),
            "history":    history(cur, req),
            "photos":     photos(cur, req),
        }


# ── Self-check ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os, json
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ["SUPABASE_HOST"], port=5432,
        user=f"postgres.{os.environ['SUPABASE_PROJECT_REF']}",
        password=os.environ["DATABASE_PASSWORD"],
        dbname="postgres", sslmode="require",
    )

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
        hist_count = len(ctx["history"])
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
