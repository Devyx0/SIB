"""
backfill_perigord_provenance.py — one-time backfill of missing provenance rows for 1580 Perigord.

The original ingest_perigord_units.py called flush() without writing the result (the buffer
was discarded). This script reconstructs the provenance rows from the source MRR + DB state.

Run:
    uv run python -m drive_pipeline.ingestion.backfill_perigord_provenance          # dry run
    uv run python -m drive_pipeline.ingestion.backfill_perigord_provenance --write
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.provenance import log_provenance, flush, flush_to_db
from drive_pipeline.ingestion.ingest_units_leases_tenants import (
    SHEET, SOURCE_TYPE, SOURCE_FILE,
    _load_rent_roll, _v,
)

_BUILDING_ID = 180


def run(dry_run: bool = True) -> None:
    print("Loading Rent Roll…")
    headers, rows_by_unit, _ = _load_rent_roll()
    perig = {k: rows_by_unit[k] for k in rows_by_unit
             if "perigord" in k.lower() or "périgord" in k.lower()}
    print(f"Perigord MRR keys: {len(perig)}")

    conn = get_conn()
    cur = conn.cursor()

    # Verify gap still exists (idempotency check)
    cur.execute("""
        SELECT COUNT(*) FROM data_provenance
        WHERE target_table = 'unit' AND target_pk::int BETWEEN
            (SELECT MIN(unit_id) FROM unit WHERE building_id=%s)
            AND (SELECT MAX(unit_id) FROM unit WHERE building_id=%s)
    """, (_BUILDING_ID, _BUILDING_ID))
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"WARNING: {existing} unit provenance rows already exist for building {_BUILDING_ID}. Aborting.")
        conn.close()
        return

    # Build (rue, apt) → unit_id map from DB
    cur.execute("""
        SELECT unit_id, rue, numero_appartement, grandeur
        FROM unit WHERE building_id=%s ORDER BY unit_id
    """, (_BUILDING_ID,))
    db_units = {}
    for unit_id, rue, apt, grandeur in cur.fetchall():
        db_units[(rue, apt)] = (unit_id, grandeur)

    print(f"DB units for building {_BUILDING_ID}: {len(db_units)}")

    # Build unit provenance
    matched = 0
    for unit_key, unit_rows in perig.items():
        first_sheet_row, first_row = unit_rows[0]
        rue = _v(first_row[2])
        apt = _v(first_row[3])
        entry = db_units.get((rue, apt))
        if entry is None:
            print(f"  SKIP (no DB match): key={unit_key!r} rue={rue!r} apt={apt!r}")
            continue
        uid, grandeur = entry
        matched += 1

        log_provenance("unit", uid, "building_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                       str(first_sheet_row), "building", str(_BUILDING_ID), str(_BUILDING_ID))
        if rue:
            log_provenance("unit", uid, "rue", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[2], rue, rue)
        if apt:
            log_provenance("unit", uid, "numero_appartement", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[3], apt, apt)
        if grandeur:
            log_provenance("unit", uid, "grandeur", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[9], grandeur, grandeur)

    print(f"Unit keys matched: {matched}/{len(perig)}")

    # Build tenancy_record provenance
    # Source row: find the sheet row for each tenant name in the MRR unit rows
    name_to_sheet_row: dict[str, str] = {}
    for unit_rows in perig.values():
        for sheet_row, row in unit_rows:
            name = _v(row[4])
            if name:
                name_to_sheet_row[name] = str(sheet_row)

    cur.execute("""
        SELECT tr.tenancy_id, tr.lease_id, tr.tenant_id, t.nom_complet
        FROM tenancy_record tr
        JOIN lease l ON l.lease_id = tr.lease_id
        JOIN unit u ON u.unit_id = l.unit_id
        JOIN tenant t ON t.tenant_id = tr.tenant_id
        WHERE u.building_id = %s
    """, (_BUILDING_ID,))
    tr_rows = cur.fetchall()
    print(f"Tenancy records for building {_BUILDING_ID}: {len(tr_rows)}")

    for tenancy_id, lease_id, tenant_id, nom_complet in tr_rows:
        src_row = name_to_sheet_row.get(nom_complet)
        log_provenance("tenancy_record", tenancy_id, "tenant_id", SOURCE_TYPE, None,
                       SOURCE_FILE, SHEET, src_row, headers[4], nom_complet, str(tenant_id))
        log_provenance("tenancy_record", tenancy_id, "lease_id", SOURCE_TYPE, None,
                       SOURCE_FILE, SHEET, src_row, headers[4], nom_complet, str(lease_id))

    prov_rows = flush()
    print(f"\nProvenance rows buffered: {len(prov_rows)}")
    if dry_run:
        print("DRY RUN — pass --write to commit")
        conn.close()
        return

    from psycopg2.extras import execute_values
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    offset = cur.fetchone()[0]
    execute_values(
        cur,
        "INSERT INTO data_provenance (provenance_id, target_table, target_pk,"
        " target_column, source_type, source_drive_id, source_file_name, source_tab,"
        " source_row, source_column, raw_value, ingested_value, ingested_at) VALUES %s",
        [(offset + i + 1, r["target_table"], r["target_pk"], r["target_column"],
          r["source_type"], r["source_drive_id"], r["source_file_name"], r["source_tab"],
          r["source_row"], r["source_column"], r["raw_value"], r["ingested_value"], None)
         for i, r in enumerate(prov_rows)],
        page_size=5000,
    )
    conn.commit()
    print(f"COMMITTED: {len(prov_rows)} provenance rows (IDs {offset+1}–{offset+len(prov_rows)})")
    conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
