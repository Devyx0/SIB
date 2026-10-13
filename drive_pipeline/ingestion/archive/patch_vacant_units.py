"""
patch_vacant_units.py — ARCHIVED (superseded 2026-09-28)

This was a one-off script to insert the 9 vacant units present only in the
French-section rows of the Master Rent Roll ("Septembre 2026" month label).

It is no longer needed. The fix to ingest_units_leases_tenants.py that widens
the month filter to accept both "September 2026" and "Septembre 2026" means the
main script now picks up all 9 units in a normal run. Any future monthly refresh
via --refresh will include them automatically.

The 9 unit_ids written by this patch (4285–4293) are NOT stable — a future
--refresh will reassign IDs by file position. That is expected and correct; see
project_status.md §5k for the unit_id stability caveat.

Original script body preserved below for reference only. Do not run.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.ingest_units_leases_tenants import (
    MRR_PATH, SHEET, SOURCE_TYPE, SOURCE_FILE,
    _v, _num, _as_date, _pet_bool,
)

# The 9 unit keys known to be in the Septembre-only section and absent from DB.
# Confirmed by exhaustive check against the 4,347 English-section unit keys.
_TARGET_UNIT_KEYS = {
    "1175-106 Chamonix",
    "3072-5 Chatelets",
    "690 Saint-Augustin",
    "786A Abraham",
    "3146-501 France-Prime",
    "220-470 Grande Allee E.",
    "220-665 Grande Allee E.",
    "220-825 Grande Allee E.",
    "220-975 Grande Allee E.",
}

_BLDG_NAME_MAP = {
    "1175 Chamonix (104 a 143)":  36,
    "3066 a 3080 Chatelets":      62,
    "690-692 Saint-Augustin":      3,
    "786-796 Abraham":             4,
    "3146 France-Prime":          93,
    "200-220 Grande Allee Est":  117,
}


def _extract_rows() -> list[tuple[int, tuple, list]]:
    """Return [(sheet_row, row_tuple, headers)] for the 9 target units."""
    wb = openpyxl.load_workbook(str(MRR_PATH), read_only=True, data_only=True)
    ws = wb[SHEET]
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    found = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        uk = _v(row[1])
        if uk in _TARGET_UNIT_KEYS:
            found.append((i, row, headers))
    wb.close()
    return found


def run(dry_run: bool = True) -> None:
    raw_rows = _extract_rows()

    conn = get_conn()
    cur = conn.cursor()

    # unit table has no unit_key column — check via numero_appartement + building_id
    already_in_db: set[str] = set()  # not checkable without unit_key; rely on ID gap

    cur.execute("SELECT COALESCE(MAX(unit_id), 0) FROM unit")
    next_unit_id = cur.fetchone()[0] + 1
    cur.execute("SELECT COALESCE(MAX(lease_id), 0) FROM lease")
    next_lease_id = cur.fetchone()[0] + 1

    units_to_insert = []
    leases_to_insert = []
    prov_rows = []

    uid = next_unit_id
    lid = next_lease_id

    print(f"\n=== patch_vacant_units {'DRY RUN' if dry_run else 'WRITE'} ===")
    print(f"\nFound {len(raw_rows)} target rows in source file.")

    for sheet_row, row, headers in raw_rows:
        unit_key = _v(row[1])
        bldg_name = _v(row[77])
        building_id = _BLDG_NAME_MAP.get(bldg_name)

        if building_id is None:
            print(f"  SKIP R{sheet_row} {unit_key!r}: building {bldg_name!r} not in map")
            continue

        avail = _v(row[76])
        print(f"  R{sheet_row}  unit_id={uid}  lease_id={lid}  {unit_key!r:<35}  "
              f"bldg_id={building_id}  avail={avail!r}")

        units_to_insert.append((uid, building_id, _v(row[2]), _v(row[3]), _v(row[9])))

        pet_raw = _v(row[70])
        leases_to_insert.append((
            lid, uid,
            _as_date(row[74]), _as_date(row[11]), _as_date(row[12]),
            _as_date(row[10]), _v(row[78]), _v(row[69]),
            _pet_bool(pet_raw), _num(row[15]), _num(row[16]),
            _num(row[49]), _v(row[13]), _num(row[51]),
            avail, _v(row[14]),
        ))

        for table, pk, col, col_idx, raw_val, db_val in [
            ("unit",  uid, "building_id",         77, bldg_name,     str(building_id)),
            ("unit",  uid, "rue",                  2, _v(row[2]),    _v(row[2])),
            ("unit",  uid, "numero_appartement",   3, _v(row[3]),    _v(row[3])),
            ("unit",  uid, "grandeur",             9, _v(row[9]),    _v(row[9])),
            ("lease", lid, "disponibilite_tableau_location", 76, avail, avail),
            ("lease", lid, "loyer_de_base",       16, _num(row[16]), _num(row[16])),
            ("lease", lid, "loyer_total",         49, _num(row[49]), _num(row[49])),
            ("lease", lid, "notes_collecte",      14, _v(row[14]),   _v(row[14])),
        ]:
            if raw_val is not None:
                prov_rows.append((
                    table, pk, col,
                    SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                    str(sheet_row), str(headers[col_idx]) if col_idx < len(headers) else col,
                    str(raw_val), str(db_val),
                ))

        uid += 1
        lid += 1

    print(f"\n  Units to insert: {len(units_to_insert)}")
    print(f"  Leases to insert: {len(leases_to_insert)}")
    print(f"  Provenance rows: {len(prov_rows)}")

    if dry_run:
        print("\n  DRY RUN — pass --write to commit.")
        conn.close()
        return

    try:
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_next = cur.fetchone()[0] + 1

        execute_values(cur,
            "INSERT INTO unit (unit_id, building_id, rue, numero_appartement, grandeur) VALUES %s",
            units_to_insert, page_size=50,
        )
        execute_values(cur,
            """INSERT INTO lease (lease_id, unit_id, debut_bail, fin_bail, date_fin_confirmee,
               date_limite_preavis, statut, langue_bail, droit_animaux, depot, loyer_de_base,
               loyer_total, mode_paiement_habituel, somme_due_restante,
               disponibilite_tableau_location, notes_collecte) VALUES %s""",
            leases_to_insert, page_size=50,
        )
        conn.commit()

        execute_values(cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            [(prov_next + i, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], None)
             for i, r in enumerate(prov_rows)],
            page_size=200,
        )
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM unit")
        print(f"\n  unit total: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM lease")
        print(f"  lease total: {cur.fetchone()[0]}")
        print(f"  Provenance rows written: {len(prov_rows)}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(
        "This script is archived and superseded.\n"
        "The 9 vacant units are now picked up by ingest_units_leases_tenants.py\n"
        "via the widened month filter. Use --refresh for monthly updates."
    )
