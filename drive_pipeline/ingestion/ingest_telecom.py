"""
ingest_telecom.py — building_telecom from File 8 (Cameras, Intercoms, Fobs... spreadsheet).

Source: work/dryrun_maintenance/Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx
Sheet:  Sommaire
Cols:   0=project, 1=address, 2=ISP, 3=broadcast, 4=tech_support, 5=telephone

Run:
    uv run python -m drive_pipeline.ingestion.ingest_telecom          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_telecom --write  # write
"""
from __future__ import annotations

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

_SRC_PATH = ROOT / "work/dryrun_maintenance/Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx"
_SRC_FILE = "Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx"
_SRC_TAB  = "Sommaire"
_SRC_DRIVE_ID = "1DqNpB_p0B7xKLqZ5IVjh5b6Jroh7Sz1M"  # File 8

def _v(val) -> str | None:
    """Return stripped string or None. Treat '-', 'N/A', 'n/a' as None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in ("-", "N/A", "n/a", "NA"):
        return None
    return s


def _norm_key(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


# File 8 address format: "StreetName [- ] CivicRange"  (reversed from DB format)
_TELECOM_ADDR_RE = re.compile(
    r"^(.+?)[\s-]+([\dàa][0-9à -]*)$",
    re.IGNORECASE,
)


def _parse_telecom_addrs(col1_raw: str):
    """
    Parse col1 which may hold one or multiple addresses in "Street - Civic" format.
    Returns list of (street, civic_str) tuples.
    """
    results = []
    # Split multi-address entries on "/" or " et "
    parts = re.split(r"\s*/\s*|\s+et\s+", col1_raw, flags=re.IGNORECASE)
    for part in parts:
        part = part.strip()
        if not part or not any(c.isdigit() for c in part):
            continue
        m = _TELECOM_ADDR_RE.match(part)
        if m:
            street = m.group(1).strip(" -")
            civic_raw = m.group(2).strip()
            # Take first civic number from ranges like "2 à 36" or "28-30"
            civic = re.split(r"[-–à ]", civic_raw)[0].strip()
            if civic.isdigit():
                results.append((street, civic))
    return results


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]
    # Check already-written telecom rows
    cur.execute("SELECT building_id FROM building_telecom")
    existing = {r[0] for r in cur.fetchall()}
    conn.close()

    wb = openpyxl.load_workbook(str(_SRC_PATH), read_only=True, data_only=True)
    ws = wb[_SRC_TAB]
    source_rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    telecom_rows = []
    prov_entries = []
    unmatched = []
    skipped_existing = 0

    for sheet_row, r in enumerate(source_rows, start=2):
        col1_raw = str(r[1]).strip() if r[1] else ""
        if not col1_raw or not any(c.isdigit() for c in col1_raw):
            continue

        isp       = _v(r[2]) if len(r) > 2 else None
        broadcast = _v(r[3]) if len(r) > 3 else None
        tech_sup  = _v(r[4]) if len(r) > 4 else None
        telephone = _v(r[5]) if len(r) > 5 else None

        if not any([isp, broadcast, tech_sup, telephone]):
            continue

        addr_pairs = _parse_telecom_addrs(col1_raw)
        if not addr_pairs:
            unmatched.append(f"row {sheet_row}: {col1_raw!r} (parse failed)")
            continue

        matched_any = False
        for street, civic in addr_pairs:
            match = _match_building(street, civic, None)
            if not match:
                continue
            building_id = bldg_by_addr.get(match.get("unique_building_name"))
            if not building_id:
                continue
            if building_id in existing:
                skipped_existing += 1
                matched_any = True
                continue

            telecom_rows.append((building_id, isp, broadcast, tech_sup, telephone))
            existing.add(building_id)
            matched_any = True

            for col_name, raw_val in [
                ("internet_provider",           isp),
                ("internet_broadcast_provider", broadcast),
                ("tech_support_provider",       tech_sup),
                ("telephone_provider",          telephone),
            ]:
                if raw_val:
                    prov_entries.append(("building_telecom", building_id, col_name,
                                         sheet_row, raw_val, raw_val))

        if not matched_any:
            unmatched.append(f"row {sheet_row}: {col1_raw!r}")

    # ── Dry run report
    print(f"\n=== ingest_telecom dry run ===")
    print(f"Source rows: {len(source_rows)}")
    print(f"Telecom rows to insert: {len(telecom_rows)}")
    print(f"Skipped (already in DB): {skipped_existing}")
    print(f"Unmatched ({len(unmatched)}):")
    for u in unmatched[:15]:
        print(f"  - {u}")
    if len(unmatched) > 15:
        print(f"  ... +{len(unmatched)-15} more")
    print(f"Provenance rows: {len(prov_entries)}")
    print("\nSample (first 10 rows):")
    for building_id, isp, broadcast, tech_sup, telephone in telecom_rows[:10]:
        print(f"  bldg={building_id}")
        if isp:       print(f"    ISP={isp[:60]!r}")
        if broadcast: print(f"    BC ={broadcast[:60]!r}")
        if tech_sup:  print(f"    TS ={tech_sup[:60]!r}")
        if telephone: print(f"    TEL={telephone[:60]!r}")

    if dry_run:
        print("\nDRY RUN — pass --write to commit.")
        return

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        execute_values(
            cur,
            """INSERT INTO building_telecom
               (building_id, internet_provider, internet_broadcast_provider,
                tech_support_provider, telephone_provider)
               VALUES %s
               ON CONFLICT (building_id) DO NOTHING""",
            telecom_rows,
            page_size=500,
        )

        prov_rows = [
            (prov_offset + i + 1,
             "building_telecom", str(table_pk), col_name,
             "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
             src_row, None, str(raw)[:2000] if raw else None,
             str(ing)[:2000] if ing else None, None)
            for i, (table_name, table_pk, col_name, src_row, raw, ing)
            in enumerate(prov_entries)
        ]
        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov_rows,
            page_size=5000,
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM building_telecom")
        print(f"Committed. building_telecom total: {cur.fetchone()[0]}")
        print(f"Provenance rows written: {len(prov_rows)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
