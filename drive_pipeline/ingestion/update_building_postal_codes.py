"""
update_building_postal_codes.py — Parse postal codes from File 4 (Oricom List)
and UPDATE building.code_postal for every matched building.

Table Fondamentale's quickbooks_address column (project.adresse_quickbooks) does NOT
contain postal codes — the addresses are truncated. File 4 is the only structured
source with full "CIVIC, street, city, POSTAL" addresses.

Run:
    uv run python -m drive_pipeline.ingestion.update_building_postal_codes          # dry run
    uv run python -m drive_pipeline.ingestion.update_building_postal_codes --write  # write
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

_FILE4_PATH = ROOT / "work/dryrun_maintenance/0 - Oricom List of Files for SIB.xlsx"
_SOURCE_FILE = "0 - Oricom List of Files for SIB.xlsx"
_SOURCE_COL  = "Address"

_QC_POSTAL = re.compile(r"\b([A-Z]\d[A-Z]\s*\d[A-Z]\d)\b", re.I)

# Oricom multi-civic addresses require manual building_id lookup:
# "786-796, Côte d'Abraham / 690, rue St-Augustin, Québec, G1R 4P2"
# → both buildings share the same postal code? Handled by address splitting below.
_GEO_PREFIX = re.compile(r"^(?:c[oô]te|chemin|route)\s+(?:d[e']?\s*)?", re.I)


def _strip_city_postal(s: str) -> str:
    """Remove postal code, province abbreviation, and city name from end of address."""
    s = _QC_POSTAL.sub("", s).strip().rstrip(" ,.")
    # Remove trailing province abbreviation (1-2 uppercase letters like "QC", "Qc")
    s = re.sub(r",?\s+[A-Z]{2}\s*$", "", s, flags=re.I).strip().rstrip(",").strip()
    # Remove trailing city/municipality name (last comma-delimited or space-delimited token
    # that is purely alphabetic + accents + hyphens — i.e. not street/civic content)
    s = re.sub(
        r",?\s+(?:Québec|Quebec|Lévis|Levis|Saint-[A-Za-zÀ-ÿ-]+|Sainte-[A-Za-zÀ-ÿ-]+)\s*$",
        "", s, flags=re.I,
    ).strip().rstrip(",").strip()
    return s


def _parse_oricom_addr(raw: str) -> list[tuple[str, str | None]]:
    """
    Parse File 4 address cell into one or more (street, civic) tuples.
    Format: "CIVIC, rue STREET [/ CIVIC2, rue STREET2], CITY, POSTAL"
    Returns list because some rows cover two buildings joined by '/'.
    """
    s = _strip_city_postal(raw.strip())

    # Split on "/" for multi-building rows
    parts = [p.strip() for p in s.split("/")]

    results = []
    for part in parts:
        part = re.sub(r"^\s*(?:au\s+|à\s+)?", "", part, flags=re.I)
        # Try "CIVIC, rue STREET" or "CIVIC, STREET"
        m = re.match(r"^([\d][\d-]*),?\s+(?:rue|boul\.|boul|av\.|av|imp\.|chemin|ch\.)\s+(.+)$", part, re.I)
        if m:
            results.append((m.group(2).strip(), m.group(1).split("-")[0]))
            continue
        # Try "CIVIC, STREET" (no street type)
        m = re.match(r"^([\d][\d-]*),?\s+(.+)$", part)
        if m:
            results.append((m.group(2).strip(), m.group(1).split("-")[0]))
            continue
        # Try plain street with no civic
        if part:
            results.append((part.strip(), None))

    return results


def _lookup_bid(street: str, civic: str | None, bldg_by_addr: dict[str, int]) -> int | None:
    result = _match_building(street, civic, None)
    if result:
        return bldg_by_addr.get(result.get("unique_building_name"))
    # French prep fallback
    m = re.match(r"^(?:de la |de l'|du |des |de |la |le |les |l')(.+)$", street, re.I)
    if m:
        result = _match_building(m.group(1).strip(), civic, None)
        if result:
            return bldg_by_addr.get(result.get("unique_building_name"))
    # Geographic prefix fallback
    gm = _GEO_PREFIX.match(street)
    if gm:
        result = _match_building(street[gm.end():].strip("' "), civic, None)
        if result:
            return bldg_by_addr.get(result.get("unique_building_name"))
    return None


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT building_id, code_postal FROM building")
    existing_postal = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]

    # ── Read File 4 ──────────────────────────────────────────────────────────
    wb = openpyxl.load_workbook(str(_FILE4_PATH), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))[1:]  # skip header
    wb.close()

    # bid → (postal_code, raw_address, file4_row)
    updates: dict[int, tuple[str, str, int]] = {}
    unmatched: list[tuple[int, str]] = []
    no_postal:  list[tuple[int, str]] = []

    for row_idx, r in enumerate(rows, start=2):
        raw = r[0]
        if not raw:
            continue
        raw_s = str(raw).strip()

        postal_m = _QC_POSTAL.search(raw_s)
        if not postal_m:
            no_postal.append((row_idx, raw_s))
            continue
        postal = postal_m.group(1).upper().replace(" ", " ")  # normalize space

        addr_parts = _parse_oricom_addr(raw_s)
        matched_bid = None
        for street, civic in addr_parts:
            bid = _lookup_bid(street, civic, bldg_by_addr)
            if bid is not None:
                matched_bid = bid
                break

        if matched_bid is None:
            unmatched.append((row_idx, raw_s))
            continue

        # Only update if not already set (or if setting to same value)
        if matched_bid not in updates:
            updates[matched_bid] = (postal, raw_s, row_idx)

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n=== building.code_postal update ===")
    print(f"File 4 data rows read:         {len(rows)}")
    print(f"  Without postal code:          {len(no_postal)}")
    print(f"  With postal code:             {len(rows) - len(no_postal)}")
    print(f"  Matched to building_id:       {len(updates)}")
    print(f"  Unmatched (no building found):{len(unmatched)}")

    already_set   = sum(1 for bid in updates if existing_postal.get(bid))
    conflict      = [(bid, existing_postal[bid], updates[bid][0])
                     for bid in updates if existing_postal.get(bid) and existing_postal[bid] != updates[bid][0]]

    print(f"\nOf {len(updates)} matched buildings:")
    print(f"  Already have code_postal:     {already_set}")
    print(f"  Will gain code_postal:        {len(updates) - already_set}")
    if conflict:
        print(f"  Conflicts (existing ≠ new):   {len(conflict)}")
        for bid, old, new in conflict:
            print(f"    building_id={bid}: existing={old!r} vs new={new!r}")

    total_bldgs = len(existing_postal)
    no_source = total_bldgs - len(updates)
    print(f"\nOf {total_bldgs} total buildings:")
    print(f"  Will have code_postal:        {len(updates)}")
    print(f"  No postal code in any source: {no_source}")

    if unmatched:
        print(f"\nUnmatched File 4 rows (building not found):")
        for er, addr in unmatched:
            print(f"  Row {er}: {addr!r}")
    if no_postal:
        print(f"\nFile 4 rows with no postal code:")
        for er, addr in no_postal:
            print(f"  Row {er}: {addr!r}")

    if dry_run:
        print(f"\nDRY RUN — {len(updates)} code_postal updates planned. Pass --write to commit.")
        conn.close()
        return

    # ── Write ─────────────────────────────────────────────────────────────────
    print(f"\nUpdating {len(updates)} building.code_postal values…")
    try:
        prov: list[tuple] = []
        pnum = prov_offset

        for bid, (postal, raw_addr, file4_row) in updates.items():
            cur.execute(
                "UPDATE building SET code_postal = %s WHERE building_id = %s",
                (postal, bid),
            )
            pnum += 1
            prov.append((
                pnum, "building", bid, "code_postal",
                "spreadsheet", None, _SOURCE_FILE, None,
                file4_row, _SOURCE_COL,
                raw_addr, postal, None,
            ))

        if prov:
            execute_values(
                cur,
                """INSERT INTO data_provenance
                   (provenance_id, target_table, target_pk, target_column,
                    source_type, source_drive_id, source_file_name, source_tab,
                    source_row, source_column, raw_value, ingested_value, ingested_at)
                   VALUES %s""",
                prov,
                page_size=500,
            )

        conn.commit()
        print(f"Committed: {len(updates)} building rows updated, {len(prov)} provenance rows.")

        cur.execute("SELECT COUNT(*) FROM building WHERE code_postal IS NOT NULL")
        print(f"Buildings with code_postal now: {cur.fetchone()[0]}/{total_bldgs}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
