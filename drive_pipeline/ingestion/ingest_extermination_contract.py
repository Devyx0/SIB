"""
ingest_extermination_contract.py — one pest service_contract (Québec Extermination)
linked to all 179 buildings.

Source: 2026-08-27 - Contrat de service - Quebec Extermination.pdf
        (Drive IDs: french=1hCYZ6KWPojsxOJhKe8NJS3q0-WqZ_a_X, english=1d2IPW-zlpZabYJYD1FkTwE_lCmZK9X_c)

Contract: QE-2026-0002-C, $5.78/unit/month, 24-month term (~2026-09-01 to 2028-08-31)
Annexe A was an empty placeholder [●] template — all 179 buildings are linked
based on "2 000 unités ou plus" language in the contract body.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_extermination_contract          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_extermination_contract --write
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn

_VENDOR_ID   = 176  # Québec Extermination
_CATEGORY    = "pest"
_TERM_START  = datetime.date(2026, 9, 1)
_TERM_END    = datetime.date(2028, 8, 31)
_COST        = 5.78          # $/unit/month
_NOTES       = (
    "Contract QE-2026-0002-C. $5.78/unit/month, 24-month term. "
    "Annexe A is an empty template (placeholder [●]) — all 179 buildings linked "
    "based on '2 000 unités ou plus' contract language."
)
_SRC_DRIVE_FR = "1hCYZ6KWPojsxOJhKe8NJS3q0-WqZ_a_X"
_SRC_FILE     = "2026-08-27 - Contrat de service - Quebec Extermination.pdf"


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(MAX(contract_id), 0) FROM service_contract")
    next_contract_id = cur.fetchone()[0] + 1

    cur.execute("SELECT building_id FROM building ORDER BY building_id")
    all_building_ids = [r[0] for r in cur.fetchall()]

    # Check if this contract already exists (idempotency)
    cur.execute(
        "SELECT contract_id FROM service_contract WHERE vendor_id = %s AND category = 'pest'",
        (_VENDOR_ID,),
    )
    existing = cur.fetchone()

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]
    conn.close()

    print(f"\n=== ingest_extermination_contract dry run ===")
    if existing:
        print(f"WARNING: pest contract for vendor {_VENDOR_ID} already exists: contract_id={existing[0]}")
        print("Pass --write to overwrite or manually reconcile.")
        return

    print(f"Contract to insert:")
    print(f"  contract_id: {next_contract_id}")
    print(f"  vendor_id:   {_VENDOR_ID}  (Québec Extermination)")
    print(f"  category:    {_CATEGORY}")
    print(f"  term:        {_TERM_START} → {_TERM_END}")
    print(f"  cost:        ${_COST}/unit/month")
    print(f"  notes:       {_NOTES[:80]}...")
    print(f"service_contract_building rows: {len(all_building_ids)} buildings")
    print(f"  building_ids: {all_building_ids[:10]} ... (all {len(all_building_ids)})")
    provenance_count = 1 + len(all_building_ids) * 2  # 1 for contract row, 2 per building link
    print(f"Provenance rows: {provenance_count}")

    if dry_run:
        print("\nDRY RUN — pass --write to commit.")
        return

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(contract_id), 0) FROM service_contract")
        next_contract_id = cur.fetchone()[0] + 1
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        cur.execute(
            """INSERT INTO service_contract
               (contract_id, vendor_id, category, term_start, term_end, cost, renews, notes)
               VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)""",
            (next_contract_id, _VENDOR_ID, _CATEGORY, _TERM_START, _TERM_END, _COST, _NOTES),
        )

        execute_values(
            cur,
            "INSERT INTO service_contract_building (contract_id, building_id) VALUES %s ON CONFLICT DO NOTHING",
            [(next_contract_id, bid) for bid in all_building_ids],
            page_size=500,
        )

        raw_annexe = "Annexe A empty template — linked from '2000 unités ou plus'"
        prov = []
        prov.append((prov_offset + 1,
                     "service_contract", str(next_contract_id), "vendor_id",
                     "document", _SRC_DRIVE_FR, _SRC_FILE, None,
                     None, None, "Québec Extermination", str(_VENDOR_ID), None))
        for i, bid in enumerate(all_building_ids):
            composite_pk = f"{next_contract_id},{bid}"
            prov.append((prov_offset + 2 + i * 2,
                         "service_contract_building",
                         composite_pk, "building_id",
                         "inferred", _SRC_DRIVE_FR, _SRC_FILE, None,
                         None, None, raw_annexe, str(bid), None))
            prov.append((prov_offset + 2 + i * 2 + 1,
                         "service_contract_building",
                         composite_pk, "contract_id",
                         "inferred", _SRC_DRIVE_FR, _SRC_FILE, None,
                         None, None, raw_annexe, str(next_contract_id), None))

        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov,
            page_size=5000,
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM service_contract_building WHERE contract_id = %s",
                    (next_contract_id,))
        print(f"Committed. contract_id={next_contract_id}, "
              f"service_contract_building rows={cur.fetchone()[0]}, "
              f"provenance={len(prov)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
