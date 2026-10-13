"""
write_maintenance_requests.py — Write Google Calendar maintenance request events to Supabase.

Phases:
  1. Schema extension (ALTER TABLE + DROP NOT NULL)
  2. Pull + parse events from Google Calendar (45-day window)
  3. Re-resolve building_id / project_id against live building/project tables
  4. Translate prose fields (parsed events only, haiku, per-event batching)
  5. Write maintenance_request rows (parsed + unparsed)
  6. Write maintenance_followup_entry rows (historique_raw / doublons)
  7. Write data_provenance rows (continues from current max provenance_id)
  8. Post-write verification

Run:
    uv run python -m drive_pipeline.ingestion.write_maintenance_requests
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.extract_raw_fields import (
    _complexity, _congestion, _delegable, _time_bucket, _report_status,
    _normalize_animals, _entry_permission,
)
from drive_pipeline.table_fondamentale.table_fondamentale import TABLE_FONDAMENTALE
import drive_pipeline.ingestion.parse_calendar_requests as _cal

# ── 1. Schema extension ───────────────────────────────────────────────────────

_DDL = [
    # Drop NOT NULL — calendar events have no unit_id; unmatched events have no building_id
    "ALTER TABLE maintenance_request ALTER COLUMN building_id DROP NOT NULL",
    "ALTER TABLE maintenance_request ALTER COLUMN unit_id DROP NOT NULL",
    # Core calendar identity
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS event_id varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS html_link text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS start_date date",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS raw_title text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS body_format varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS parse_status varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS source_calendar_id varchar",
    # Title-extracted fields
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS assigned_employee_code_raw varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS urgency_raw varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS civic varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS street_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS problem_summary text",
    # v10 / belanger_compact body sections
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS problems text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS entry_permission text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS animals text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS occupants_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS bail_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS ft_link text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS ft_name text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS historique_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS tri_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS delegable_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS report_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS doublons text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS synergie_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS complexite_raw varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS embourbement_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS gravity_raw text",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS signed_date varchar",
    # Gravity Forms-specific
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS submission_date varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS caller_type varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS caller_email varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS fees_advised varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS category_raw varchar",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS address_urgency text",
    # Unique index: idempotency guard on Google Calendar event ID
    "CREATE UNIQUE INDEX IF NOT EXISTS mr_event_id_key ON maintenance_request(event_id) WHERE event_id IS NOT NULL",
]


def _extend_schema(conn) -> None:
    cur = conn.cursor()
    # Skip if already set up — avoids ACCESS EXCLUSIVE lock on maintenance_request on repeat runs
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='maintenance_request' AND column_name='event_id'""")
    if cur.fetchone():
        print("Schema already extended — skipping DDL.")
        return
    cur.execute("SET statement_timeout = 0")
    for ddl in _DDL:
        cur.execute(ddl)
    conn.commit()
    print(f"Schema extended: {len(_DDL)} DDL statements applied.")


# ── 2. Live-table lookup ──────────────────────────────────────────────────────

def _load_live(conn) -> tuple[dict, dict, dict, int]:
    """Return (live_bldg, live_proj, unit_index, max_provenance_id).

    live_bldg:  adresse → {building_id, project_id, sector_id}
    live_proj:  lower(nom_unique_projet) → project_id
    unit_index: prebuilt lookup tables for unit_id resolution (see build_unit_index)
    """
    cur = conn.cursor()
    cur.execute("SELECT building_id, adresse, project_id, sector_id FROM building")
    live_bldg = {
        r[1]: {"building_id": r[0], "project_id": r[2], "sector_id": r[3]}
        for r in cur.fetchall()
    }
    cur.execute("SELECT project_id, nom_unique_projet FROM project")
    live_proj = {r[1].lower(): r[0] for r in cur.fetchall()}
    unit_index = _cal.build_unit_index(conn)
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    max_prov_id = cur.fetchone()[0]
    return live_bldg, live_proj, unit_index, max_prov_id


# TF row index (1-based) for delta detection
_TF_IDX: dict[str, int] = {
    row["unique_building_name"]: i + 1
    for i, row in enumerate(TABLE_FONDAMENTALE)
}


def _resolve(
    record: dict,
    live_bldg: dict,
    live_proj: dict,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Return (building_id, project_id, sector_id, tf_expected_building_id).

    tf_expected_building_id is what we'd infer from TF row order alone;
    building_id is the live-DB-confirmed value. Report delta if they differ.
    """
    tf_match = record.get("tf_match")  # unique_building_name from TF

    building_id = project_id = sector_id = tf_expected = None

    if tf_match:
        b = live_bldg.get(tf_match)
        if b:
            building_id = b["building_id"]
            project_id = b["project_id"]
            sector_id = b["sector_id"]
        tf_expected = _TF_IDX.get(tf_match)

    # Override project from PROJET body section if resolvable
    proj_label = record.get("projet")
    if proj_label:
        pid = live_proj.get(proj_label.lower().strip())
        if pid:
            project_id = pid

    return building_id, project_id, sector_id, tf_expected


# ── 3. Event → DB row ─────────────────────────────────────────────────────────

def _parse_date(start: str | None) -> str | None:
    return start[:10] if start else None


_MR_COLS = [
    "request_id",
    "source_calendar", "source_calendar_id", "event_id", "html_link",
    "start_date", "body_format", "parse_status", "raw_title",
    "building_id", "project_id", "sector_id", "unit_id",
    "assigned_employee_code_raw", "urgency_raw", "urgency_tier",
    "civic", "street_raw", "unit_label", "project_label",
    "problem_summary", "problems", "entry_permission", "animals",
    "occupants_raw", "bail_raw", "ft_link", "ft_name",
    "historique_raw", "tri_raw", "triage_summary",
    "delegable_raw", "report_raw", "doublons", "synergie_raw",
    "time_estimate_raw", "complexite_raw",
    "subcontractor_name", "proposed_assignee", "other_notes",
    "embourbement_raw", "gravity_raw", "signed_date",
    "caller_name", "caller_phone", "caller_email", "caller_type",
    "category_raw", "address_urgency", "submission_date", "fees_advised",
    # Derived at ingest time from raw columns above
    "complexity_tier", "congestion_level", "delegable_status",
    "time_estimate_bucket", "report_status",
]

_SQL_MR = (
    f"INSERT INTO maintenance_request ({', '.join(_MR_COLS)}) "
    f"VALUES ({', '.join(['%s'] * len(_MR_COLS))}) "
    f"ON CONFLICT DO NOTHING"
)

# urgency_tier enum accepts only these values
_URGENCY_TIER_VALS = {"AJD", "ajd", "none"}


def _event_to_row(
    record: dict,
    request_id: int,
    building_id: int | None,
    project_id: int | None,
    sector_id: int | None,
    unit_id: int | None,
) -> tuple:
    fmt = record.get("body_format", "")
    is_parsed = fmt != "unparsed_body_format"

    urgency = record.get("urgency")
    urgency_raw = urgency or record.get("urgency_raw")
    urgency_tier_val = urgency if urgency in _URGENCY_TIER_VALS else None

    unit_lbl = (
        record.get("unite")
        or record.get("unit")
        or record.get("unit_number")
    )

    triage = record.get("tri") if is_parsed else None
    if not triage and fmt == "gravity_forms":
        triage = record.get("message")

    row = {
        "request_id":               request_id,
        "source_calendar":          record.get("calendar_key"),
        "source_calendar_id":       record.get("calendar_id"),
        "event_id":                 record.get("event_id"),
        "html_link":                record.get("html_link"),
        "start_date":               _parse_date(record.get("start")),
        "body_format":              fmt,
        "parse_status":             "parsed" if is_parsed else "unparsed",
        "raw_title":                record.get("raw_title"),
        "building_id":              building_id,
        "project_id":               project_id,
        "sector_id":                sector_id,
        "unit_id":                  unit_id,
        "assigned_employee_code_raw": record.get("employee_code"),
        "urgency_raw":              urgency_raw,
        "urgency_tier":             urgency_tier_val,
        "civic":                    record.get("civic"),
        "street_raw":               record.get("street"),
        "unit_label":               unit_lbl,
        "project_label":            record.get("projet"),
        "problem_summary":          record.get("problem_summary"),
        "problems":                 record.get("problems"),
        "entry_permission":         _entry_permission(record.get("entry_permission")),
        "animals":                  _normalize_animals(record.get("animals")),
        "occupants_raw":            record.get("occupants_raw"),
        "bail_raw":                 record.get("bail_raw"),
        "ft_link":                  record.get("ft_link"),
        "ft_name":                  record.get("ft_name"),
        "historique_raw":           record.get("historique_raw"),
        "tri_raw":                  record.get("tri"),
        "triage_summary":           triage,
        "delegable_raw":            record.get("delegable"),
        "report_raw":               record.get("report"),
        "doublons":                 record.get("doublons"),
        "synergie_raw":             record.get("synergie_raw"),
        "time_estimate_raw":        record.get("temps"),
        "complexite_raw":           record.get("complexite"),
        "subcontractor_name":       record.get("sous_traitant"),
        "proposed_assignee":        record.get("assignation"),
        "other_notes":              record.get("autres_notes"),
        "embourbement_raw":         record.get("embourbement"),
        "gravity_raw":              record.get("gravity_raw"),
        "signed_date":              record.get("signed_date"),
        "caller_name":              record.get("caller_name"),
        "caller_phone":             record.get("caller_phone"),
        "caller_email":             record.get("caller_email"),
        "caller_type":              record.get("caller_type"),
        "category_raw":             record.get("category_raw"),
        "address_urgency":          record.get("address_urgency"),
        "submission_date":          record.get("submission_date"),
        "fees_advised":             record.get("fees_advised"),
        # Derived from raw triage text at ingest time
        "complexity_tier":          _complexity(record.get("complexite")),
        "congestion_level":         _congestion(record.get("embourbement")),
        "delegable_status":         _delegable(record.get("delegable")),
        "time_estimate_bucket":     _time_bucket(record.get("temps")),
        "report_status":            _report_status(record.get("report")),
    }
    return tuple(row[c] for c in _MR_COLS)


# ── 4. Provenance ─────────────────────────────────────────────────────────────

_SQL_PROV = """
    INSERT INTO data_provenance
        (provenance_id, target_table, target_pk, target_column,
         source_type, source_drive_id, source_file_name, source_tab,
         source_row, source_column, raw_value, ingested_value, ingested_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT DO NOTHING
"""

# (record_key, db_column, source_column_label, is_prose)
# is_prose=True means raw_value ≠ ingested_value after translation
_PROV_FIELDS = [
    ("raw_title",        "raw_title",       "title",                    False),
    ("employee_code",    "assigned_employee_code_raw", "title",         False),
    ("urgency",          "urgency_raw",     "title",                    False),
    ("civic",            "civic",           "title",                    False),
    ("street",           "street_raw",      "title",                    False),
    ("problem_summary",  "problem_summary", "title",                    False),
    ("problems",         "problems",        "PROBLEMES",                True),
    ("entry_permission", "entry_permission","PERMISSION",               True),
    ("animals",          "animals",         "ANIMAUX",                  True),
    ("occupants_raw",    "occupants_raw",   "OCCUPANTS",                False),
    ("bail_raw",         "bail_raw",        "BAIL",                     False),
    ("ft_link",          "ft_link",         "FICHE TECHNIQUE",          False),
    ("ft_name",          "ft_name",         "FICHE TECHNIQUE",          False),
    ("historique_raw",   "historique_raw",  "HISTORIQUE",               True),
    ("tri",              "tri_raw",         "TRI",                      True),
    ("delegable",        "delegable_raw",   "DELEGABLE",                True),
    ("report",           "report_raw",      "REPORT",                   True),
    ("doublons",         "doublons",        "DOUBLONS",                 True),
    ("synergie_raw",     "synergie_raw",    "SYNERGIE",                 False),
    ("unite",            "unit_label",      "UNITE",                    False),
    ("projet",           "project_label",   "PROJET",                   False),
    ("temps",            "time_estimate_raw","TEMPS",                   False),
    ("complexite",       "complexite_raw",  "COMPLEXITE",               False),
    ("sous_traitant",    "subcontractor_name","SOUS-TRAITANT",          False),
    ("assignation",      "proposed_assignee","ASSIGNATION PROPOSEE",    False),
    ("autres_notes",     "other_notes",     "AUTRES NOTES",             True),
    ("embourbement",     "embourbement_raw","EMBOURBEMENT",             True),
    ("gravity_raw",      "gravity_raw",     "description",              False),
    ("signed_date",      "signed_date",     "BELANGER",                 False),
    # Gravity Forms
    ("message",          "triage_summary",  "Commentaires",             True),
    ("caller_name",      "caller_name",     "Nom complet",              False),
    ("caller_phone",     "caller_phone",    "Telephone",                False),
    ("caller_email",     "caller_email",    "Courriel",                 False),
    ("caller_type",      "caller_type",     "Type appelant",            False),
    ("urgency_raw",      "urgency_raw",     "Urgent ou non-urgent",     False),
    ("category_raw",     "category_raw",    "Categorie",                False),
    ("address_urgency",  "address_urgency", "Adresse urgence",          False),
    ("submission_date",  "submission_date", "Date et heure",            False),
    ("fees_advised",     "fees_advised",    "Frais",                    False),
]

# (raw_record_key, db_col, raw_col_label, extractor) — written with source_type='derived'
_PROV_DERIVED = [
    ("complexite",   "complexity_tier",      "complexite_raw",    _complexity),
    ("embourbement", "congestion_level",      "embourbement_raw",  _congestion),
    ("delegable",    "delegable_status",      "delegable_raw",     _delegable),
    ("temps",        "time_estimate_bucket",  "time_estimate_raw", _time_bucket),
    ("report",       "report_status",         "report_raw",        _report_status),
]


def _provenance_rows(
    record: dict,
    raw_values: dict,
    request_id: int,
    cal_id: str,
    html_link: str,
    prov_id_start: int,
) -> list[tuple]:
    rows = []
    pid = prov_id_start
    for rec_key, db_col, src_col, is_prose in _PROV_FIELDS:
        raw = raw_values.get(rec_key) if is_prose else record.get(rec_key)
        ingested = record.get(rec_key) if is_prose else raw
        if raw is None and ingested is None:
            continue
        rows.append((
            pid,
            "maintenance_request", request_id, db_col,
            "google_calendar", cal_id, None, None,
            html_link, src_col,
            str(raw) if raw is not None else None,
            str(ingested) if ingested is not None else None,
        ))
        pid += 1

    # Derived columns — source_type='derived', source_column=raw col name
    for rec_key, db_col, raw_col_label, extractor in _PROV_DERIVED:
        raw = record.get(rec_key)
        derived = extractor(raw)
        if derived is None:
            continue
        rows.append((
            pid,
            "maintenance_request", request_id, db_col,
            "derived", None, "write_maintenance_requests.py", None,
            None, raw_col_label,
            str(raw)[:1000] if raw is not None else None,
            str(derived),
        ))
        pid += 1

    return rows


# ── 5. Main write ─────────────────────────────────────────────────────────────

def write_all(start_dt=None, end_dt=None, translate: bool = True) -> None:
    # ── Schema extension ──────────────────────────────────────────────────────
    conn = get_conn()
    _extend_schema(conn)
    conn.close()

    # ── Pull + parse events ───────────────────────────────────────────────────
    from datetime import timedelta
    window_desc = "45-day window" if start_dt is None else f"{start_dt.date()}→{(end_dt - timedelta(days=1)).date()}"
    print(f"Pulling events from Google Calendar ({window_desc})...")
    results = _cal.run(dry_run=True, silent=True, start_dt=start_dt, end_dt=end_dt)

    parsed   = [r for r in results if r["body_format"] != "unparsed_body_format"]
    unparsed = [r for r in results if r["body_format"] == "unparsed_body_format"]
    print(f"Events: {len(parsed)} parsed, {len(unparsed)} unparsed, {len(results)} total")

    fmt_counts: dict[str, int] = {}
    for r in results:
        fmt_counts[r["body_format"]] = fmt_counts.get(r["body_format"], 0) + 1
    print("Format breakdown:")
    for fmt, n in sorted(fmt_counts.items(), key=lambda x: -x[1]):
        print(f"  {fmt:<30} {n:>5}")

    # ── Load live lookup + resolve ────────────────────────────────────────────
    conn = get_conn()
    live_bldg, live_proj, unit_index, max_prov_id = _load_live(conn)
    conn.close()
    print(f"Live lookup: {len(live_bldg)} buildings, {len(live_proj)} projects, "
          f"{len(unit_index['civic_apt'])} unit civic+apt entries, "
          f"max_provenance_id={max_prov_id}")

    # Resolve + delta check (before translation, purely on structural data)
    delta_changes: list[dict] = []
    resolutions: list[tuple] = []  # (building_id, project_id, sector_id)
    matched_count = unmatched_count = 0

    for record in results:
        bid, pid, sid, tf_exp = _resolve(record, live_bldg, live_proj)
        resolutions.append((bid, pid, sid))
        if bid is not None:
            matched_count += 1
        else:
            unmatched_count += 1
        # Delta: TF index-based expected vs live-resolved actual
        if tf_exp is not None and bid is not None and bid != tf_exp:
            delta_changes.append({
                "event_id": record["event_id"],
                "tf_match": record["tf_match"],
                "live_building_id": bid,
                "tf_expected": tf_exp,
            })

    print(f"Building resolution: {matched_count} matched, {unmatched_count} unmatched")
    print(f"Building_id re-resolution delta (live vs TF-index): {len(delta_changes)} changed")
    if delta_changes:
        for d in delta_changes:
            print(f"  event={d['event_id']!r}  tf_match={d['tf_match']!r}  "
                  f"live={d['live_building_id']}  tf_idx_expected={d['tf_expected']}")

    # ── Translate prose fields (parsed events only) ───────────────────────────
    raw_values_list: list[dict] = []
    if translate:
        print(f"Translating prose fields for {len(parsed)} parsed events...")
        for i, record in enumerate(results):
            if record["body_format"] != "unparsed_body_format":
                raw_vals = {k: record.get(k) for k in _cal._TRANSLATE_PROSE_FIELDS}
                _cal._translate_prose_fields(record)
            else:
                raw_vals = {}
            raw_values_list.append(raw_vals)
            if (i + 1) % 100 == 0:
                print(f"  translated {i+1}/{len(results)}...", flush=True)
        print("Translation complete.")
    else:
        print("Translation skipped (translate=False); prose fields stored as-is.")
        for record in results:
            raw_values_list.append({k: record.get(k) for k in _cal._TRANSLATE_PROSE_FIELDS}
                                   if record["body_format"] != "unparsed_body_format" else {})

    # ── DB write ──────────────────────────────────────────────────────────────
    from psycopg2.extras import execute_values

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Start IDs from current max to avoid PK collisions on re-runs / second batches
        cur.execute("SELECT COALESCE(MAX(request_id), 0) FROM maintenance_request")
        request_id_start = cur.fetchone()[0] + 1
        cur.execute("SELECT COALESCE(MAX(followup_id), 0) FROM maintenance_followup_entry")
        followup_id_start = cur.fetchone()[0] + 1

        prov_id = max_prov_id + 1
        all_mr_rows: list[tuple] = []
        all_prov_rows: list[tuple] = []
        followup_rows: list[tuple] = []
        followup_id = followup_id_start

        for i, (record, (bid, pid, sid), raw_vals) in enumerate(
            zip(results, resolutions, raw_values_list), request_id_start
        ):
            unit_lbl = (record.get("unite") or record.get("unit") or record.get("unit_number"))
            unit_id = _cal.resolve_unit_id(unit_lbl, bid, unit_index)
            all_mr_rows.append(_event_to_row(record, i, bid, pid, sid, unit_id))

            # Provenance
            html_link = record.get("html_link") or ""
            cal_id = record.get("calendar_id") or ""
            prov_batch = _provenance_rows(record, raw_vals, i, cal_id, html_link, prov_id)
            all_prov_rows.extend(prov_batch)
            prov_id += len(prov_batch)

            if unit_id is not None and unit_lbl:
                all_prov_rows.append((
                    prov_id,
                    "maintenance_request", i, "unit_id",
                    "derived", None, None, None, None, "unit_label",
                    str(unit_lbl), str(unit_id),
                ))
                prov_id += 1

            # Followup entries from historique_raw and doublons
            start_date = _parse_date(record.get("start"))
            for field in ("historique_raw", "doublons"):
                text = record.get(field)
                if text:
                    followup_rows.append((followup_id, i, text, start_date, None))
                    followup_id += 1

        print(f"Rows built: {len(all_mr_rows)} MR, {len(followup_rows)} followup, "
              f"{len(all_prov_rows)} provenance — bulk inserting...", flush=True)

        # Bulk insert maintenance_request
        _MR_COLS_str = ", ".join(_MR_COLS)
        execute_values(
            cur,
            f"INSERT INTO maintenance_request ({_MR_COLS_str}) VALUES %s ON CONFLICT DO NOTHING",
            all_mr_rows, page_size=500,
        )
        print(f"  maintenance_request inserted", flush=True)

        # Bulk insert followup entries
        if followup_rows:
            execute_values(
                cur,
                "INSERT INTO maintenance_followup_entry "
                "(followup_id, request_id, entry_text, entry_date, entered_by_initials) "
                "VALUES %s ON CONFLICT DO NOTHING",
                followup_rows, page_size=500,
            )
        print(f"  maintenance_followup_entry inserted", flush=True)

        # Bulk insert provenance — tuples have 12 values; ingested_at appended as None (nullable)
        _PROV_COLS = (
            "provenance_id, target_table, target_pk, target_column, "
            "source_type, source_drive_id, source_file_name, source_tab, "
            "source_row, source_column, raw_value, ingested_value, ingested_at"
        )
        execute_values(
            cur,
            f"INSERT INTO data_provenance ({_PROV_COLS}) VALUES %s ON CONFLICT DO NOTHING",
            [row + (None,) for row in all_prov_rows], page_size=1000,
        )
        print(f"  data_provenance inserted", flush=True)

        conn.commit()
        print(f"\nCommitted:")
        print(f"  maintenance_request       {len(all_mr_rows):>6} rows (starting id={request_id_start})")
        print(f"  maintenance_followup_entry{len(followup_rows):>6} rows")
        print(f"  data_provenance           {len(all_prov_rows):>6} new rows")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # ── Post-write verification ───────────────────────────────────────────────
    _verify(len(results), fmt_counts, delta_changes)


def _verify(n_written: int, fmt_counts: dict, delta_changes: list) -> None:
    print("\n" + "=" * 70)
    print("POST-WRITE VERIFICATION (live Supabase)")
    print("=" * 70)

    conn = get_conn()
    cur = conn.cursor()

    # 1. Row counts
    cur.execute("SELECT COUNT(*) FROM maintenance_request")
    mr_total = cur.fetchone()[0]
    cur.execute("SELECT parse_status, body_format, COUNT(*) FROM maintenance_request GROUP BY parse_status, body_format ORDER BY parse_status, body_format")
    breakdown = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM maintenance_followup_entry")
    fu_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM data_provenance WHERE target_table='maintenance_request'")
    prov_total = cur.fetchone()[0]

    print(f"\n── Row counts ──")
    print(f"  maintenance_request:        {mr_total}  (intended: {n_written})")
    print(f"  maintenance_followup_entry: {fu_total}")
    print(f"  data_provenance (mr only):  {prov_total}")
    print(f"\n── parse_status × body_format breakdown ──")
    for r in breakdown:
        print(f"  parse_status={r[0]!r:<10} body_format={r[1]!r:<25} n={r[2]}")

    # 2. Building_id re-resolution delta (already reported above; confirm here)
    print(f"\n── Building_id re-resolution delta ──")
    print(f"  Changes vs TF-index ordering: {len(delta_changes)}")

    # 3. Orphaned FK check
    print(f"\n── Orphaned FK check ──")
    cur.execute("""
        SELECT COUNT(*) FROM maintenance_request mr
        WHERE mr.building_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM building b WHERE b.building_id = mr.building_id)
    """)
    orphan_bldg = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM maintenance_request mr
        WHERE mr.project_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM project p WHERE p.project_id = mr.project_id)
    """)
    orphan_proj = cur.fetchone()[0]
    print(f"  Orphaned building_id refs: {orphan_bldg}  (expect 0)")
    print(f"  Orphaned project_id refs:  {orphan_proj}  (expect 0)")

    # 4. Exclusion confirmation — excluded categories must have 0 rows
    print(f"\n── Excluded category confirmation ──")
    cur.execute("""
        SELECT COUNT(*) FROM maintenance_request
        WHERE raw_title LIKE '!%'
    """)
    admin_rows = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM maintenance_request
        WHERE raw_title ~* '^X(?:\\s|[A-Z]|$)'
    """)
    x_rows = cur.fetchone()[0]
    print(f"  Rows with admin '!' prefix: {admin_rows}  (expect 0)")
    print(f"  Rows with 'X' in-execution prefix: {x_rows}  (expect 0)")

    # 5. Spot-check sample — 10 rows, ≥1 per parsed format
    print(f"\n── Spot-check: 10 rows (≥1 per format) ──")
    cur.execute("""
        SELECT request_id, parse_status, body_format, start_date, raw_title,
               building_id, project_id, assigned_employee_code_raw, html_link
        FROM maintenance_request
        ORDER BY
            CASE body_format
                WHEN 'v10'              THEN 1
                WHEN 'v10_plaintext'    THEN 2
                WHEN 'belanger_compact' THEN 3
                WHEN 'gravity_forms'    THEN 4
                ELSE 5
            END,
            request_id
        LIMIT 10
    """)
    for r in cur.fetchall():
        rid, ps, fmt, dt, title, bid, pid, emp, link = r
        print(f"\n  request_id={rid}  parse_status={ps!r}  body_format={fmt!r}")
        print(f"    date={dt}  building_id={bid}  project_id={pid}")
        print(f"    employee={emp!r}")
        print(f"    title={str(title)[:80]!r}")
        link_s = str(link)[:80] if link else None
        print(f"    link={link_s!r}")

    # 6. Provenance spot-check: first parsed event's provenance rows
    cur.execute("""
        SELECT target_column, source_type, source_column, raw_value, ingested_value
        FROM data_provenance
        WHERE target_table='maintenance_request' AND target_pk=1
        ORDER BY provenance_id
        LIMIT 10
    """)
    rows = cur.fetchall()
    print(f"\n── Provenance spot-check: request_id=1 (first {len(rows)} rows) ──")
    for r in rows:
        col, st, sc, raw, ing = r
        raw_s = (raw[:50] + "...") if raw and len(raw) > 50 else raw
        ing_s = (ing[:50] + "...") if ing and len(ing) > 50 else ing
        print(f"  col={col!r:<30} src_col={sc!r:<25} raw={raw_s!r}")
        if ing != raw:
            print(f"  {'':30} {'':25} ing={ing_s!r}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    write_all()
