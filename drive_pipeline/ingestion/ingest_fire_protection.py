"""
ingest_fire_protection.py — Dry-run and write ingestion for two tables:
  - building_fire_system  (one row per building)
  - service_visit         (one row per building with due_date or completed_date)

Source: work/dryrun_maintenance/Fire_Protection_EN.xlsx, sheet 'MASTER 1'

Run:
    uv run python -m drive_pipeline.ingestion.ingest_fire_protection          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_fire_protection --write  # write
"""
from __future__ import annotations

import datetime
import re
import sys
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

_FIRE_PATH = ROOT / "work/dryrun_maintenance/Fire_Protection_EN.xlsx"
_SOURCE_FILE = "Fire_Protection_EN.xlsx"
_SOURCE_TAB  = "MASTER 1"

_CIVIC_RE = re.compile(r"^(\d+(?:[-–]\d+)*)\s+(.+)")

# norm_key(alias) → norm_key(canonical) for vendors whose aliases aren't in the DB nom
_VENDOR_ALIASES = {
    "protek": "yprotek",  # "Pro Tek" → "Y Pro-Tek"
}


def _norm_key(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _v(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _date(v) -> datetime.date | None:
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return None


def _vendor_id(raw, vendor_by_norm: dict) -> int | None:
    v = _v(raw)
    if not v or v.upper() in ("N/A", "NA", "N/A (NONE)"):
        return None
    nk = _norm_key(v)
    vid = vendor_by_norm.get(nk)
    if vid is None:
        aliased = _VENDOR_ALIASES.get(nk)
        if aliased:
            vid = vendor_by_norm.get(aliased)
    return vid


def _parse_civic_street(addr: str):
    """Return (civic, street) from a simple address string, or (None, None)."""
    # Strip city suffix after comma
    addr = addr.split(",")[0].strip()
    # Take first part for multi-address (e.g. "A / B")
    addr = addr.split("/")[0].strip()
    m = _CIVIC_RE.match(addr)
    if m:
        return m.group(1), m.group(2).strip()
    return None, None


def _resolve_building(nom_unique: str | None, proj_addr: str | None,
                      bldg_by_addr: dict) -> int | None:
    if nom_unique:
        bid = bldg_by_addr.get(nom_unique)
        if bid:
            return bid

    # Fallback 1: _match_building via Project Address
    if proj_addr:
        civic, street = _parse_civic_street(proj_addr)
        if civic and street:
            row = _match_building(street, civic, None)
            if row:
                bid = bldg_by_addr.get(row.get("unique_building_name"))
                if bid:
                    return bid

    # Fallback 2: civic + street-prefix match (handles truncated names like
    # "843 Hypolite" → "843 Hypolite-Bernier", "1940 Cardinal" → "1940 Cardinal-Villeneuve")
    nom = nom_unique or proj_addr
    if nom:
        m = _CIVIC_RE.match(nom)
        if m:
            first_civic = m.group(1).split("-")[0]
            street_pfx = m.group(2).lower()[:6]
            for addr, bid in bldg_by_addr.items():
                am = _CIVIC_RE.match(addr)
                if (am and am.group(1).split("-")[0] == first_civic
                        and am.group(2).lower().startswith(street_pfx)):
                    return bid
    return None


def _load(conn):
    cur = conn.cursor()
    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT vendor_id, nom FROM vendor_contact")
    vendor_by_norm = {_norm_key(nom): vid for vid, nom in cur.fetchall()}
    cur.execute("SELECT COALESCE(MAX(fire_system_id), 0) FROM building_fire_system")
    fs_start = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(visit_id), 0) FROM service_visit")
    visit_start = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_start = cur.fetchone()[0]
    return bldg_by_addr, vendor_by_norm, fs_start, visit_start, prov_start


def _is_text_note(val) -> bool:
    """Return True if val is a text string (not a date object and not a digit string)."""
    if val is None:
        return False
    import datetime
    if isinstance(val, (datetime.date, datetime.datetime)):
        return False
    s = str(val).strip()
    return bool(s) and not s.isdigit()


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    bldg_by_addr, vendor_by_norm, fs_start, visit_start, prov_start = _load(conn)
    conn.close()

    wb = openpyxl.load_workbook(str(_FIRE_PATH), read_only=True, data_only=True)
    ws = wb["MASTER 1"]
    source_rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    fire_system_rows = []  # (fire_system_id, building_id, fields...)
    visit_rows       = []  # (visit_id, building_id, vendor_id, ...)
    prov_entries     = []  # (target_table, target_pk, col, src_row, raw, ingested)
    unmatched        = []
    vendor_misses    = set()

    for sheet_row, r in enumerate(source_rows, start=2):
        nom_unique = _v(r[4]) if len(r) > 4 else None
        proj_addr  = _v(r[2]) if len(r) > 2 else None

        building_id = _resolve_building(nom_unique, proj_addr, bldg_by_addr)
        if building_id is None:
            unmatched.append(nom_unique or proj_addr or f"row {sheet_row}")
            continue

        # ── vendor lookups
        spr_vid  = _vendor_id(r[14] if len(r) > 14 else None, vendor_by_norm)
        co2_vid  = _vendor_id(r[18] if len(r) > 18 else None, vendor_by_norm)
        fire_vid = _vendor_id(r[20] if len(r) > 20 else None, vendor_by_norm)

        for col_idx, raw_v, vid in ((14, r[14] if len(r) > 14 else None, spr_vid),
                                     (18, r[18] if len(r) > 18 else None, co2_vid),
                                     (20, r[20] if len(r) > 20 else None, fire_vid)):
            v = _v(raw_v)
            if v and v.upper() not in ("N/A", "NA") and vid is None:
                vendor_misses.add(v)

        notes_raw = _v(r[21]) if len(r) > 21 else None
        piezzo    = _v(r[11]) if len(r) > 11 else None

        fs_id = fs_start + len(fire_system_rows) + 1
        fs = (
            fs_id, building_id,
            _v(r[8])  if len(r) > 8  else None,   # panel_brand_model
            _v(r[9])  if len(r) > 9  else None,   # panel_control_status
            _v(r[10]) if len(r) > 10 else None,   # emergency_panel_status
            _v(r[12]) if len(r) > 12 else None,   # smoke_detector_status
            _v(r[13]) if len(r) > 13 else None,   # sprinkler_status
            spr_vid,                               # sprinkler_vendor_id
            _v(r[15]) if len(r) > 15 else None,   # hose_status
            _v(r[16]) if len(r) > 16 else None,   # pressurization_pump_status
            _v(r[17]) if len(r) > 17 else None,   # co2_status
            co2_vid,                               # co2_vendor_id
            _v(r[19]) if len(r) > 19 else None,   # dossier_link
            fire_vid,                              # current_fire_vendor_id
            _date(r[7] if len(r) > 7 else None),              # corrective_actions_date
            piezzo,                                # piezzo_status
            notes_raw,                             # notes
        )
        fire_system_rows.append(fs)

        # Provenance for fire_system: key fields
        for col_name, raw_val, ingested_val in [
            ("building_id",         nom_unique,                  building_id),
            ("panel_brand_model",   r[8] if len(r) > 8 else None, _v(r[8] if len(r) > 8 else None)),
            ("sprinkler_vendor_id", r[14] if len(r) > 14 else None, spr_vid),
            ("current_fire_vendor_id", r[20] if len(r) > 20 else None, fire_vid),
        ]:
            if raw_val is not None or col_name == "building_id":
                prov_entries.append(("building_fire_system", fs_id, col_name,
                                     sheet_row, raw_val, ingested_val))

        # ── service_visit: only if due_date or completed_date present
        due_date       = r[5] if len(r) > 5 else None
        completed_date = r[6] if len(r) > 6 else None
        if due_date is not None or completed_date is not None:
            # deficiencies: text from col[7] if it's a note, else notes
            corrective = r[7] if len(r) > 7 else None
            if _is_text_note(corrective):
                deficiencies = str(corrective).strip()
            else:
                deficiencies = notes_raw  # fallback to fire system notes

            vid_row = visit_start + len(visit_rows) + 1
            visit_rows.append((
                vid_row, building_id, fire_vid, None,
                "fire_inspection",
                _date(due_date), _date(completed_date),
                None,          # result
                deficiencies,
                None,          # next_due_date
            ))
            prov_entries.append(("service_visit", vid_row, "building_id",
                                 sheet_row, nom_unique, building_id))
            prov_entries.append(("service_visit", vid_row, "due_date",
                                 sheet_row, due_date, _date(due_date)))
            prov_entries.append(("service_visit", vid_row, "completed_date",
                                 sheet_row, completed_date, _date(completed_date)))

    # ── Dry run report
    print(f"\n=== ingest_fire_protection dry run ===")
    print(f"Source rows processed: {len(source_rows)}")
    print(f"Matched buildings:     {len(fire_system_rows)} / {len(source_rows)}")
    if unmatched:
        print(f"Unmatched ({len(unmatched)}):")
        for u in unmatched:
            print(f"  - {u}")
    print(f"building_fire_system rows: {len(fire_system_rows)}")
    print(f"service_visit rows:        {len(visit_rows)}")
    print(f"provenance rows:           {len(prov_entries)}")
    if vendor_misses:
        print(f"Vendor names not resolved ({len(vendor_misses)}):")
        for v in sorted(vendor_misses):
            print(f"  - {v!r}")
    print("\nSample (first 5 fire_system rows):")
    for fs in fire_system_rows[:5]:
        print(f"  fs_id={fs[0]} bldg={fs[1]} panel={fs[2]!r} "
              f"sprinkler={fs[6]!r} spr_vid={fs[7]} fire_vid={fs[13]}")

    if dry_run:
        print(f"\nDRY RUN — pass --write to commit.")
        return

    # ── Write
    conn = get_conn()
    try:
        cur = conn.cursor()
        # Re-fetch offsets in case another process wrote between dry run and write
        cur.execute("SELECT COALESCE(MAX(fire_system_id), 0) FROM building_fire_system")
        fs_start = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(visit_id), 0) FROM service_visit")
        visit_start = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        # Recompute IDs from fresh offsets
        for i, fs in enumerate(fire_system_rows):
            fire_system_rows[i] = (fs_start + i + 1,) + fs[1:]
        for i, v in enumerate(visit_rows):
            visit_rows[i] = (visit_start + i + 1,) + v[1:]

        execute_values(
            cur,
            """INSERT INTO building_fire_system
               (fire_system_id, building_id, panel_brand_model, panel_control_status,
                emergency_panel_status, smoke_detector_status, sprinkler_status,
                sprinkler_vendor_id, hose_status, pressurization_pump_status,
                co2_status, co2_vendor_id, dossier_link, current_fire_vendor_id,
                corrective_actions_date, piezzo_status, notes)
               VALUES %s""",
            fire_system_rows,
            page_size=500,
        )

        execute_values(
            cur,
            """INSERT INTO service_visit
               (visit_id, building_id, vendor_id, equipment_id, visit_type,
                due_date, completed_date, result, deficiencies, next_due_date)
               VALUES %s""",
            visit_rows,
            page_size=500,
        )

        # Rebuild prov with correct IDs — map by row index
        fs_id_map = {i: fire_system_rows[i][0] for i in range(len(fire_system_rows))}
        visit_id_map = {i: visit_rows[i][0] for i in range(len(visit_rows))}

        all_prov = []
        fs_counter = visit_counter = 0
        for table, pk, col, src_row, raw, ingested in prov_entries:
            all_prov.append((
                None,  # provenance_id set below
                table, pk, col,
                "spreadsheet", None, _SOURCE_FILE, _SOURCE_TAB,
                src_row, col, str(raw) if raw is not None else None,
                str(ingested) if ingested is not None else None,
                None,
            ))

        for chunk_start in range(0, len(all_prov), 5000):
            chunk = all_prov[chunk_start:chunk_start + 5000]
            execute_values(
                cur,
                """INSERT INTO data_provenance
                   (provenance_id, target_table, target_pk, target_column,
                    source_type, source_drive_id, source_file_name, source_tab,
                    source_row, source_column, raw_value, ingested_value, ingested_at)
                   VALUES %s""",
                [(prov_offset + chunk_start + i + 1,
                  r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12])
                 for i, r in enumerate(chunk)],
                page_size=5000,
            )

        conn.commit()
        print(f"Committed: {len(fire_system_rows)} building_fire_system, "
              f"{len(visit_rows)} service_visit, {len(all_prov)} provenance rows.")
        cur.execute("SELECT COUNT(*) FROM building_fire_system")
        print(f"building_fire_system total: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM service_visit")
        print(f"service_visit total: {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
