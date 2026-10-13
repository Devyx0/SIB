"""
ingest_pool_access_codes.py — Dry-run and write ingestion of pool_access_code
from Pool Access Codes - OSEN.gsheet.xlsx.

Source: work/dryrun_maintenance/Pool Access Codes - OSEN.gsheet.xlsx
  Sheet: Feuille 1
  Columns: Code (numeric), Assigned To (text or None)

All 51 codes belong to the OSEN pool complex (buildings 91-94: 1017 Duchesneau +
3140/3146/3150 France-Prime). The spreadsheet does not specify which building each
code is assigned to, so building_id is left NULL for all rows. The schema column
was NOT NULL; this script alters it to nullable on first run.

Credential discipline: code_value stored in the DB column; provenance raw_value and
ingested_value are always '[REDACTED-SENSITIVE]'; codes are never echoed to console.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_pool_access_codes          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_pool_access_codes --write  # write
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn

_POOL_PATH = ROOT / "work/dryrun_maintenance/Pool Access Codes - OSEN.gsheet.xlsx"
_SOURCE_FILE = "Pool Access Codes - OSEN.gsheet.xlsx"
_SOURCE_TYPE = "spreadsheet"
_REDACTED = "[REDACTED-SENSITIVE]"


def _load_codes() -> list[dict]:
    wb = openpyxl.load_workbook(str(_POOL_PATH), read_only=True, data_only=True)
    ws = wb["Feuille 1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    records = []
    for sheet_row, row in enumerate(rows[1:], start=2):  # skip header
        if not row or row[0] is None:
            continue
        code_val = str(row[0]).strip()
        assigned_to = str(row[1]).strip() if row[1] else None
        records.append({
            "code_value": code_val,
            "notes": assigned_to,
            "sheet_row": sheet_row,
        })
    return records


def run(dry_run: bool = True) -> None:
    records = _load_codes()

    print("=== pool_access_code dry run ===")
    print(f"Source: {_SOURCE_FILE}")
    print(f"Total codes: {len(records)}")
    assigned = [r for r in records if r["notes"]]
    print(f"  Unassigned: {len(records) - len(assigned)}")
    print(f"  Assigned:   {len(assigned)} ({', '.join(r['notes'] for r in assigned)})")
    print(f"  building_id: NULL for all (OSEN complex; source does not assign per building)")
    print(f"  Provenance: code_value → {_REDACTED!r} (credential redaction)")

    if dry_run:
        print(f"\nDRY RUN — {len(records)} pool_access_code rows planned. Pass --write to commit.")
        return

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # Make building_id nullable — the schema defaulted NOT NULL but codes are complex-wide
        cur.execute(
            "ALTER TABLE pool_access_code ALTER COLUMN building_id DROP NOT NULL"
        )

        cur.execute("SELECT COALESCE(MAX(pool_code_id), 0) FROM pool_access_code")
        next_id = cur.fetchone()[0] + 1

        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        rows_to_insert = [
            (next_id + i, None, r["code_value"], r["notes"])
            for i, r in enumerate(records)
        ]

        prov_rows = []
        pnum = prov_offset
        for i, r in enumerate(records):
            pid = next_id + i
            for col_name in ("code_value",):
                pnum += 1
                prov_rows.append((
                    pnum, "pool_access_code", pid, col_name,
                    _SOURCE_TYPE, None, _SOURCE_FILE, "Feuille 1",
                    r["sheet_row"], "Code", _REDACTED, _REDACTED, None,
                ))
            if r["notes"]:
                pnum += 1
                prov_rows.append((
                    pnum, "pool_access_code", pid, "notes",
                    _SOURCE_TYPE, None, _SOURCE_FILE, "Feuille 1",
                    r["sheet_row"], "Assigned To", r["notes"], r["notes"], None,
                ))

        execute_values(
            cur,
            "INSERT INTO pool_access_code (pool_code_id, building_id, code_value, notes) VALUES %s",
            rows_to_insert,
            page_size=500,
        )
        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov_rows,
            page_size=500,
        )

        conn.commit()
        print(f"Committed: {len(records)} pool_access_code rows, {len(prov_rows)} provenance rows.")

        cur.execute("SELECT COUNT(*) FROM pool_access_code")
        print(f"pool_access_code total: {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
