"""
ingest_elevator_contracts.py — Dry-run and write ingestion of service_contract
and service_contract_building from Elevator_Contracts_EN.xlsx.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_elevator_contracts          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_elevator_contracts --write  # write
"""
from __future__ import annotations

import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

_ELEV_PATH = ROOT / "work/dryrun_maintenance/Elevator_Contracts_EN.xlsx"
_SOURCE_FILE = "Elevator_Contracts_EN.xlsx"
_SOURCE_TAB  = "Feuil1"


def _norm_key(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _parse_cost(val) -> float | None:
    if val is None:
        return None
    s = str(val).split("\n")[0].strip()
    s = s.replace("$", "").replace(" ", "").replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _as_date(val) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def _parse_address(desc: str):
    """Return (civic, street) from 'CIVIC STREET' desc column."""
    m = re.match(r'^(\d+(?:-\d+)?)\s+(.+)$', desc.strip())
    if m:
        return m.group(1), m.group(2)
    return None, desc.strip()


_FRENCH_PREP = re.compile(r'^(?:de la |de l\'|du |des |de |la |le |les |l\')', re.I)


def _lookup_building(desc: str, bldg_by_addr: dict) -> int | None:
    civic, street = _parse_address(desc)

    def _try(s, c):
        r = _match_building(s, c, None)
        if r:
            return bldg_by_addr.get(r.get("unique_building_name"))
        return None

    bid = _try(street, civic)
    if bid:
        return bid

    # Fallback 1: strip French prepositions from street (e.g. "de L'Arsenal" → "Arsenal")
    street2 = _FRENCH_PREP.sub("", street).strip()
    if street2 != street:
        bid = _try(street2, civic)
        if bid:
            return bid

    # Fallback 2: range civic "M-N" → try first number (e.g. "410-420" → "410")
    if civic and "-" in civic:
        bid = _try(street, civic.split("-")[0])
        if bid:
            return bid

    return None


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    # Load lookups
    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT vendor_id, nom FROM vendor_contact")
    vendor_by_norm = {_norm_key(nom): vid for vid, nom in cur.fetchall()}

    cur.execute("SELECT COALESCE(MAX(contract_id), 0) FROM service_contract")
    next_id = cur.fetchone()[0] + 1

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]

    # Read source
    wb = openpyxl.load_workbook(str(_ELEV_PATH), read_only=True, data_only=True)
    ws = wb["Feuil1"]
    source_rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    contracts   = []   # (contract_id, vendor_id, term_end, cost, notes, sheet_row, customer_raw, cost_raw)
    scb_rows    = []   # (contract_id, building_id, desc, sheet_row)
    unmatched_bldg   = []
    unmatched_vendor = []

    for sheet_row, r in enumerate(source_rows, start=2):
        desc     = r[1]
        customer = r[2]

        # filter: need real description and a customer
        if not desc or str(desc).strip() in ("", "None"):
            continue
        if not customer or str(customer).strip() in ("", "None"):
            continue

        desc_s = str(desc).strip()
        customer_s = str(customer).strip()

        # skip free-text noise rows (many words, clearly not vendor names)
        if customer_s.count(" ") > 5:
            continue

        # vendor lookup
        vendor_id = vendor_by_norm.get(_norm_key(customer_s))
        if vendor_id is None:
            unmatched_vendor.append((sheet_row, customer_s))
            continue  # vendor_id NOT NULL in schema

        # building lookup
        building_id = _lookup_building(desc_s, bldg_by_addr)
        if building_id is None:
            unmatched_bldg.append((sheet_row, desc_s))

        # term_end
        term_end = _as_date(r[12]) or _as_date(r[14])

        # cost
        cost_raw = r[7]
        cost = _parse_cost(cost_raw)

        # notes
        note_parts = []
        if r[0] is not None:  note_parts.append(f"Contract #{r[0]}")
        if r[6] is not None:  note_parts.append(f"Coverage: {r[6]}")
        if r[8] is not None:  note_parts.append(f"Payment: {r[8]}")
        if r[13] is not None: note_parts.append(f"Duration: {r[13]}")
        notes = "; ".join(note_parts) if note_parts else None

        cid = next_id
        next_id += 1
        contracts.append((cid, vendor_id, term_end, cost, notes, sheet_row, customer_s, cost_raw))

        if building_id is not None:
            scb_rows.append((cid, building_id, desc_s, sheet_row))
        else:
            # contract written, building link skipped
            pass

    # ── Dry run report
    print("\n=== elevator_contracts dry run ===")
    print(f"Valid source rows processed: {len(contracts) + len(unmatched_vendor)}")
    print(f"Vendor matches:   {len(contracts)}/{len(contracts) + len(unmatched_vendor)}")
    if unmatched_vendor:
        for sr, v in unmatched_vendor:
            print(f"  UNMATCHED vendor row {sr}: {v!r}")
    print(f"Building matches: {len(scb_rows)}/{len(contracts)}")
    if unmatched_bldg:
        for sr, d in unmatched_bldg:
            print(f"  UNMATCHED building row {sr}: {d!r}")
    print(f"service_contract rows planned:          {len(contracts)}")
    print(f"service_contract_building rows planned: {len(scb_rows)}")
    print()
    print("Full contract list:")
    for cid, vid, term_end, cost, notes, sr, cust, _ in contracts:
        bldg = next((b for (c, b, _, __) in scb_rows if c == cid), None)
        print(f"  [contract_id={cid}] vendor_id={vid} ({cust!r}) building_id={bldg} "
              f"cost={cost} term_end={term_end}")

    if dry_run:
        print(f"\nDRY RUN — {len(contracts)} service_contract, {len(scb_rows)} service_contract_building, "
              f"pass --write to commit.")
        conn.close()
        return

    # ── Write
    print(f"\nWriting {len(contracts)} service_contract rows…")
    try:
        execute_values(
            cur,
            """INSERT INTO service_contract
               (contract_id, vendor_id, category, term_start, term_end, cost, renews, notes)
               VALUES %s""",
            [(cid, vid, "elevator", None, term_end, cost, None, notes)
             for cid, vid, term_end, cost, notes, *_ in contracts],
            page_size=500,
        )

        if scb_rows:
            execute_values(
                cur,
                "INSERT INTO service_contract_building (contract_id, building_id) VALUES %s",
                [(cid, bid) for cid, bid, *_ in scb_rows],
                page_size=500,
            )

        # Provenance
        prov = []
        pnum = prov_offset
        for cid, vid, term_end, cost, notes, sr, cust, cost_raw in contracts:
            for col, raw, ingested in [
                ("vendor_id", cust, str(vid)),
                ("category", None, "elevator"),
                ("term_end", None, str(term_end) if term_end else None),
                ("cost", str(cost_raw) if cost_raw is not None else None, str(cost) if cost is not None else None),
            ]:
                pnum += 1
                prov.append((pnum, "service_contract", str(cid), col,
                              "spreadsheet", None, _SOURCE_FILE, _SOURCE_TAB,
                              sr, col, raw, ingested, None))

        for cid, bid, desc, sr in scb_rows:
            composite_pk = f"{cid},{bid}"
            pnum += 1
            prov.append((pnum, "service_contract_building", composite_pk, "building_id",
                          "spreadsheet", None, _SOURCE_FILE, _SOURCE_TAB,
                          sr, "Description", desc, str(bid), None))
            pnum += 1
            prov.append((pnum, "service_contract_building", composite_pk, "contract_id",
                          "spreadsheet", None, _SOURCE_FILE, _SOURCE_TAB,
                          sr, "Description", desc, str(cid), None))

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
        print(f"Committed: {len(contracts)} service_contract, {len(scb_rows)} service_contract_building, "
              f"{len(prov)} provenance rows.")

        cur.execute("SELECT COUNT(*) FROM service_contract")
        print(f"service_contract total: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM service_contract_building")
        print(f"service_contract_building total: {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
