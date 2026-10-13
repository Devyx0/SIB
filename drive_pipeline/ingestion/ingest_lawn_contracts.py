"""
ingest_lawn_contracts.py — service_contract rows from Soumission_pelouse_2026.xlsx.

Single sheet "2024-2025":
  col0: building address (multiline)
  col1: selected vendor name
  col2: confirmed price / notes (format: "vendor\nprice\ndetails" OR "Inclus dans...")
  Row 1 headers: vendor names every 6 columns starting at col 7
  Row 2 sub-headers: Ménage Stat / Ménage Terrain / Tonte / Feuilles / Plates-Bandes / Total - Soumission

Price priority:
  1. col2 second line (if it looks like a number)
  2. Selected vendor's "Total - Soumission" column (vendor_col + 5)
  3. None reported in dry run

Run:
    uv run python -m drive_pipeline.ingestion.ingest_lawn_contracts          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_lawn_contracts --write
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

_SRC_PATH     = ROOT / "work/dryrun_maintenance/Soumission_pelouse_2026.xlsx"
_SRC_FILE     = "Soumission_pelouse_2026.xlsx"
_SRC_TAB      = "2024-2025"
_SRC_DRIVE_ID = "1LcDq_dYMtN_wMb-bgndacERvbDPlqKQ9"
_CATEGORY     = "lawn"

_CIVIC_RE  = re.compile(r"^(\d+(?:[-–à ]\d+)*)\s+(.+)")
_INCLUS_RE = re.compile(r"^inclus|^voir", re.I)
_PRICE_RE  = re.compile(r"([\d\s,]+)(?:\$|,00)")
_JUNK_VENDOR_RE = re.compile(
    r"^(n/a|pas de|aucun|inclus|voir|pdt-|\d+\s*[mM]2)",
    re.I,
)

# Vendor name aliases: norm_key(variant) → canonical_name.
# Must stay in sync with ingest_snow_contracts._ALIASES.
_ALIASES: dict[str, str] = {
    # MPCH group
    "entreprisempchneige":          "MPCH",
    "monpayscestlhivermpch":        "MPCH",
    "artisantdupaysagempchneige":   "MPCH",
    # T.B. Multi-Service
    "tbmultiservicetbmultiservice": "T.B. Multi-Service",
    # Joe Pelletier
    "joepelletier":                 "Excavation Joe Pelletier",
    # La Québécoise
    "lesentrepriseslaquebecoise":   "La Québécoise",
    "laquebecoise":                 "La Québécoise",
    # Entretien G.F. — lawn has "Entretien GF" short form
    "entretretienmultiservicesgf":  "Entretien G.F.",
    "entretiengf":                  "Entretien G.F.",
    # Les cent Frontières — lawn has "Les Cents Frontieres" (plural typo)
    "lescentsfrontieres":           "Les cent Frontières",
}


def _is_real_vendor(name: str) -> bool:
    if not name or len(name) > 80:
        return False
    return not _JUNK_VENDOR_RE.search(name)


def _norm_key(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _v(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _addr_first_line(raw: str) -> str:
    for line in raw.split("\n"):
        line = line.strip()
        if line and any(c.isdigit() for c in line):
            return line
    return raw.split("\n")[0].strip()


def _parse_civic_street(addr: str):
    first_line = addr.split("\n")[0].strip().split("(")[0].strip()
    if "," in first_line:
        street_part, civic_part = first_line.split(",", 1)
        street = street_part.strip()
        civic = re.split(r"[-–à ]", civic_part.strip())[0].strip()
        if street and civic.isdigit():
            return civic, street
    m = _CIVIC_RE.match(first_line)
    if m:
        return m.group(1), m.group(2).strip()
    m2 = re.match(r"^(.+?)\s+(\d+(?:[-–]\d+)?)\s*$", first_line)
    if m2:
        civic = re.split(r"[-–]", m2.group(2))[0].strip()
        if civic.isdigit():
            return civic, m2.group(1).strip()
    return None, None


def _match(addr_raw: str, bldg_by_addr: dict):
    line = _addr_first_line(addr_raw)
    civic, street = _parse_civic_street(line)
    if not civic or not street:
        return None
    row = _match_building(street, civic, None)
    if not row:
        return None
    return bldg_by_addr.get(row.get("unique_building_name"))


def _extract_price_from_str(s: str):
    """Extract a float from a string like '800$ +tx' or '1 830$ +tx' or '1000.0'."""
    if not s:
        return None
    s_clean = s.replace("\xa0", "").replace(" ", "").replace("$", "")
    # Float already
    m = re.match(r"^([\d,]+\.?\d*)$", s_clean)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    # Leading digits+comma
    m2 = re.match(r"([\d,]+)", s_clean)
    if m2:
        try:
            return float(m2.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def _extract_price_from_col2(col2: str, selected_vendor: str):
    """
    col2 is a pasted vendor confirmation email: line1=vendor_name, line2=price, line3+=terms.
    We only use line2 as the price if line1's vendor name matches the selected vendor (col1).
    A mismatch means a competitor's quote was pasted in — fall through to the vendor grid.

    Returns (price_float, price_note, is_bundled).
    """
    if not col2:
        return None, "empty", False
    lines = [l.strip() for l in col2.split("\n") if l.strip()]
    if not lines:
        return None, "empty", False
    if _INCLUS_RE.match(lines[0]):
        return None, "bundled", True
    # Bare price on line1 (no vendor header)
    if lines[0] and lines[0][0].isdigit():
        p = _extract_price_from_str(lines[0])
        return p, "col2_line1", False
    # Line1 is a vendor name — only proceed if it matches the selected vendor
    if len(lines) > 1 and _norm_key(lines[0]) == _norm_key(selected_vendor):
        for ln in lines[1:]:
            if ln and ln[0].isdigit():
                p = _extract_price_from_str(ln)
                if p is not None:
                    return p, "col2_line2", False
            m = re.search(r"[Tt]otal\s*:?\s*([\d,\s]+)", ln)
            if m:
                p = _extract_price_from_str(m.group(1).strip())
                if p is not None:
                    return p, "col2_total", False
    return None, "col2_no_price", False


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT vendor_id, nom FROM vendor_contact")
    vendor_by_norm = {_norm_key(nom): vid for vid, nom in cur.fetchall()}
    cur.execute("SELECT COALESCE(MAX(contract_id), 0) FROM service_contract")
    contract_start = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]
    conn.close()

    wb = openpyxl.load_workbook(str(_SRC_PATH), read_only=True, data_only=True)
    ws = wb.active

    # Build vendor column map from row 1 headers (col 7+ every 6 cols, up to ~212)
    header_row = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))[0]
    vendor_col_map = {}  # norm_key → column_index
    for j in range(7, len(header_row)):
        val = header_row[j]
        if val and isinstance(val, str) and val.strip():
            # Only accept if it's a vendor-name cell (not a sub-header)
            first_line = val.strip().split("\n")[0].strip()
            nk = _norm_key(first_line)
            if nk and nk not in vendor_col_map:
                vendor_col_map[nk] = j

    source_rows = list(ws.iter_rows(min_row=3, values_only=True))
    wb.close()

    main_contracts = []
    bundled_rows   = []
    unmatched      = []
    new_vendors    = {}

    for row_idx, r in enumerate(source_rows):
        row_num = row_idx + 3
        addr_raw = _v(r[0]) if r[0] else None
        if not addr_raw or not any(c.isdigit() for c in addr_raw):
            continue

        vendor_raw = str(r[1]).strip().split("\n")[0].strip() if r[1] else ""
        col2_raw   = str(r[2]).strip() if r[2] else ""

        if not vendor_raw or not _is_real_vendor(vendor_raw):
            continue

        building_id = _match(addr_raw, bldg_by_addr)
        if building_id is None:
            unmatched.append(f"row {row_num}: {_addr_first_line(addr_raw)!r}")
            continue

        price, price_note, is_bundled = _extract_price_from_col2(col2_raw, vendor_raw)

        if is_bundled:
            # Extract reference address from col2
            lines = [l.strip() for l in col2_raw.split("\n") if l.strip()]
            ref = lines[1] if len(lines) > 1 else lines[0]
            bundled_rows.append({
                "building_id": building_id,
                "addr": addr_raw,
                "ref_addr_hint": ref,
                "vendor_raw": vendor_raw,
                "row_num": row_num,
            })
            continue

        # Fallback: try vendor comparison column
        if price is None:
            vnk = _norm_key(vendor_raw.split("\n")[0].strip())
            vcol = vendor_col_map.get(vnk)
            if vcol is not None and vcol + 5 < len(r):
                total_val = r[vcol + 5]
                if total_val is not None:
                    p = _extract_price_from_str(str(total_val).split("\n")[0].strip())
                    if p is not None:
                        price = p
                        price_note = "vendor_col"

        raw_nk   = _norm_key(vendor_raw)
        canonical = _ALIASES.get(raw_nk, vendor_raw) if raw_nk else vendor_raw
        canon_nk  = _norm_key(canonical) if canonical else ""
        vid = vendor_by_norm.get(canon_nk) if canon_nk else None
        if canon_nk and vid is None:
            new_vendors[canon_nk] = canonical

        main_contracts.append({
            "building_id": building_id,
            "addr": addr_raw,
            "vendor_raw": vendor_raw,
            "vendor_nk": canon_nk,
            "price": price,
            "price_note": price_note,
            "col2": col2_raw,
            "row_num": row_num,
        })

    # Try to resolve bundled rows against main contracts
    main_by_bid = {c["building_id"]: i for i, c in enumerate(main_contracts)}
    bundled_links   = []  # (main_idx, building_id)
    bundled_miss    = []
    for br in bundled_rows:
        # Try matching ref_addr_hint to a building
        ref_bid = _match(br["ref_addr_hint"], bldg_by_addr)
        if ref_bid and ref_bid in main_by_bid:
            bundled_links.append((main_by_bid[ref_bid], br["building_id"]))
        else:
            bundled_miss.append(
                f"row {br['row_num']}: {_addr_first_line(br['addr'])!r} → ref {br['ref_addr_hint']!r} unresolved"
            )

    price_ok   = [c for c in main_contracts if c["price"] is not None]
    price_miss = [c for c in main_contracts if c["price"] is None]

    # ── Dry run report
    print(f"\n=== ingest_lawn_contracts dry run ===")
    print(f"Source rows processed: {len(source_rows)}")
    print(f"Main contract rows:    {len(main_contracts)}")
    print(f"  With price:          {len(price_ok)}")
    print(f"  No price found:      {len(price_miss)}")
    print(f"Bundled rows:          {len(bundled_rows)}")
    print(f"  Resolved:            {len(bundled_links)}")
    print(f"  Unresolved:          {len(bundled_miss)}")
    print(f"New vendors to add:    {len(new_vendors)}")
    for nk, nom in sorted(new_vendors.items(), key=lambda x: x[1]):
        print(f"  {nom!r}")
    print(f"Unmatched buildings:   {len(unmatched)}")
    for u in unmatched[:10]:
        print(f"  {u}")

    print("\n--- 10 price extraction samples ---")
    for c in main_contracts[:10]:
        addr_line = _addr_first_line(c["addr"])[:40]
        price_disp = f"${c['price']:.2f} ({c['price_note']})" if c["price"] else f"NONE ({c['price_note']})"
        print(f"  {addr_line!r}")
        print(f"    vendor: {c['vendor_raw'][:50]!r}")
        print(f"    price:  {price_disp}  col2={c['col2'][:60]!r}")

    print("\n--- No-price rows (sample) ---")
    for c in price_miss[:5]:
        addr_line = _addr_first_line(c["addr"])[:40]
        print(f"  {addr_line!r} vendor={c['vendor_raw'][:40]!r} col2={c['col2'][:50]!r}")

    if dry_run:
        print("\nDRY RUN — pass --write to commit.")
        return

    # ── Write
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT vendor_id, nom FROM vendor_contact")
        vendor_by_norm = {_norm_key(nom): vid for vid, nom in cur.fetchall()}
        cur.execute("SELECT COALESCE(MAX(contract_id), 0) FROM service_contract")
        contract_start = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(vendor_id), 0) FROM vendor_contact")
        vid_start = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        # Insert new vendors (canonical names only — aliases already collapsed above)
        for i, (nk, nom) in enumerate(new_vendors.items()):
            new_vid = vid_start + i + 1
            cur.execute("INSERT INTO vendor_contact (vendor_id, nom) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (new_vid, nom))
            vendor_by_norm[nk] = new_vid

        # Insert contracts (vendor_id is nullable — write even when vendor is blank)
        contract_rows = []
        contract_id_map = {}
        for i, c in enumerate(main_contracts):
            vid   = vendor_by_norm.get(c["vendor_nk"]) if c["vendor_nk"] else None
            notes = c["col2"][:1000] if c["col2"] else None
            if vid is None and c.get("vendor_raw"):
                notes = f"[vendor unmatched: {c['vendor_raw']!r}] " + (notes or "")
            cid = contract_start + len(contract_rows) + 1
            contract_rows.append((
                cid, vid, _CATEGORY,
                None, None,  # term_start, term_end
                c["price"],
                False,
                notes,
            ))
            contract_id_map[i] = cid

        execute_values(
            cur,
            """INSERT INTO service_contract
               (contract_id, vendor_id, category, term_start, term_end, cost, renews, notes)
               VALUES %s ON CONFLICT DO NOTHING""",
            contract_rows,
            page_size=500,
        )

        # Building links: main contracts
        bldg_link_rows = [(contract_id_map[i], c["building_id"])
                          for i, c in enumerate(main_contracts)
                          if i in contract_id_map]
        # Bundled building links
        for main_idx, bid in bundled_links:
            cid = contract_id_map.get(main_idx)
            if cid:
                bldg_link_rows.append((cid, bid))

        execute_values(
            cur,
            "INSERT INTO service_contract_building (contract_id, building_id) VALUES %s ON CONFLICT DO NOTHING",
            bldg_link_rows,
            page_size=500,
        )

        # Provenance
        prov_rows = []
        for i, c in enumerate(main_contracts):
            cid = contract_id_map.get(i)
            if not cid:
                continue
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract", str(cid), "cost",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
                c["row_num"], 2, c["col2"][:2000] if c["col2"] else None,
                str(c["price"]) if c["price"] else None, None,
            ))
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract", str(cid), "vendor_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
                c["row_num"], 1, c["vendor_raw"], str(vendor_by_norm.get(c["vendor_nk"])), None,
            ))
            composite_pk = f"{cid},{c['building_id']}"
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract_building", composite_pk, "building_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
                c["row_num"], 0, None, str(c["building_id"]), None,
            ))
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract_building", composite_pk, "contract_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
                c["row_num"], 0, None, str(cid), None,
            ))

        for main_idx, bid in bundled_links:
            cid = contract_id_map.get(main_idx)
            if not cid:
                continue
            c = main_contracts[main_idx]
            composite_pk = f"{cid},{bid}"
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract_building", composite_pk, "building_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
                c["row_num"], 0, None, str(bid), None,
            ))
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract_building", composite_pk, "contract_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, _SRC_TAB,
                c["row_num"], 0, None, str(cid), None,
            ))

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
        print(f"Committed: {len(contract_rows)} contracts, "
              f"{len(bldg_link_rows)} building links, {len(prov_rows)} provenance rows.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
