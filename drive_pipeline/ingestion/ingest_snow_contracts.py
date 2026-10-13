"""
ingest_snow_contracts.py — service_contract rows from Soumission_deneigement_2026-27.xlsx.

Two tabs → two categories:
  Stationnement → 'snow_parking'  (parking lot snow removal)
  Piétonnier    → 'snow_pedestrian' (pedestrian path snow removal)

Col layout (both tabs):
  col0: building address (multiline)
  col1: validation status ("Validée" = approved)
  col4: selected vendor name (first line; may be empty)
  col5: price/terms string (may embed 2026-27 amount)

Only rows where col1 contains "validée" or "appro" are written.
Bundled rows ("Inclus dans le contrat de...") are linked to their parent contract.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_snow_contracts          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_snow_contracts --write
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

_SRC_PATH     = ROOT / "work/dryrun_maintenance/Soumission_deneigement_2026-27.xlsx"
_SRC_FILE     = "Soumission_deneigement_2026-27.xlsx"
_SRC_DRIVE_ID = "1DaiUyHImjn0BRbpoLr8vP1WHHN2ChZKp"

_CIVIC_RE = re.compile(r"^(\d+(?:[-–à ]\d+)*)\s+(.+)")
_INCLUS_RE = re.compile(r"^i[no]?cl[ui]s", re.I)  # handles "Inclus" and "Iuclus" (typo)

TABS = [
    ("Stationnement", "snow_parking"),
    ("Piétonnier",    "snow_pedestrian"),
]


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
    # Format 1 (most common): "StreetName, CivicRange\nPostalCode"
    first_line = addr.split("\n")[0].strip().split("(")[0].strip()
    if "," in first_line:
        street_part, civic_part = first_line.split(",", 1)
        street = street_part.strip()
        civic_raw = civic_part.strip()
        civic = re.split(r"[-–à ]", civic_raw)[0].strip()
        if street and civic.isdigit():
            return civic, street
    # Format 2: "Civic Street" (leading digit)
    m = _CIVIC_RE.match(first_line)
    if m:
        return m.group(1), m.group(2).strip()
    # Format 3: "StreetName Civic" (no comma, civic at end)
    m2 = re.match(r"^(.+?)\s+(\d+(?:[-–]\d+)?)\s*$", first_line)
    if m2:
        civic = re.split(r"[-–]", m2.group(2))[0].strip()
        if civic.isdigit():
            return civic, m2.group(1).strip()
    return None, None


def _clean_vendor(raw: str) -> str:
    """First non-empty line, strip extra whitespace."""
    for line in raw.split("\n"):
        line = line.strip()
        if line:
            return line
    return raw.strip()


_JUNK_VENDOR_RE = re.compile(
    r"^(n/a|pas de|on (faisait|ne )?d[eé]n|inclus|voir|pdt-|info de|\d+\s*[mM]2)",
    re.I,
)

# Vendor name aliases: norm_key(variant) → canonical_name to store in DB.
# All variants in a group collapse to one vendor_contact row.
_ALIASES: dict[str, str] = {
    # MPCH group (4 surface forms → one company)
    "entreprisempchneige":          "MPCH",
    "monpayscestlhivermpch":        "MPCH",
    # T.B. Multi-Service — source has a doubled-name typo
    "tbmultiservicetbmultiservice": "T.B. Multi-Service",
    # Joe Pelletier — person name vs company name
    "joepelletier":                 "Excavation Joe Pelletier",
    # La Québécoise — formal vs short (accent-normalised keys are already equal,
    # but the informal "Les entreprises" prefix needs explicit aliasing)
    "lesentrepriseslaquebecoise":   "La Québécoise",
    "laquebecoise":                 "La Québécoise",
    # Entretien G.F. — snow has a "Entretretien" typo variant
    "entretretienmultiservicesgf":  "Entretien G.F.",
}


def _is_real_vendor(name: str) -> bool:
    """Filter out placeholder/note strings that got into the vendor column."""
    if not name or len(name) > 80:
        return False
    if _JUNK_VENDOR_RE.search(name):
        return False
    return True


def _extract_price(price_str: str):
    """Return (amount_float, extraction_note) or (None, reason)."""
    if not price_str:
        return None, "empty"
    # Bundled row — not a price
    if _INCLUS_RE.match(price_str):
        return None, "bundled"
    # 2026-27 or 2026-2027 explicit amount
    m = re.search(r"2026[-–](?:27|2027)\s*:?\s*([\d\xa0\s,]+)", price_str)
    if m:
        raw = m.group(1).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            return float(raw), "2026-27"
        except ValueError:
            pass
    # Leading number (no multi-year breakdown in string)
    m2 = re.match(r"([\d,]+)", price_str.replace("\xa0", "").replace(" ", ""))
    if m2:
        raw = m2.group(1).replace(",", ".")
        try:
            return float(raw), "leading"
        except ValueError:
            pass
    return None, "parse_error"


def _is_approved(col1_val: str) -> bool:
    v = (col1_val or "").lower()
    return "valid" in v or "appro" in v


def _match(addr_raw: str, bldg_by_addr: dict):
    """Return (building_id, matched_name) or (None, None)."""
    line = _addr_first_line(addr_raw)
    civic, street = _parse_civic_street(line)
    if not civic or not street:
        return None, None
    row = _match_building(street, civic, None)
    if not row:
        return None, None
    name = row.get("unique_building_name")
    return bldg_by_addr.get(name), name


def _parse_tab(ws, bldg_by_addr: dict, use_col8_vendor: bool = False):
    """
    Returns:
      main_contracts: list of dicts with building_id, vendor_raw, price, price_note, price_str, approved, addr
      bundled_rows:   list of dicts with building_id, ref_addr (what they reference), addr
      unmatched:      list of str
    use_col8_vendor: True for Piétonnier (col8 = "Déneigement 2025-2026" = more recent vendor)
    """
    main_contracts = []
    bundled_rows   = []
    unmatched      = []

    for row_num, r in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        addr_raw = _v(r[0]) if r[0] else None
        if not addr_raw or not any(c.isdigit() for c in addr_raw):
            continue  # sector header or empty

        col1    = _v(r[1]) or ""
        vendor4 = _clean_vendor(_v(r[4]) or "") if r[4] else ""
        price_str = _v(r[5]) or ""

        if use_col8_vendor:
            col8 = _clean_vendor(_v(r[8]) or "") if len(r) > 8 and r[8] else ""
            vendor = col8 if col8 else vendor4
        else:
            vendor = vendor4
        approved = _is_approved(col1)

        building_id, _ = _match(addr_raw, bldg_by_addr)

        if building_id is None:
            unmatched.append(f"row {row_num}: {_addr_first_line(addr_raw)!r}")
            continue

        if _INCLUS_RE.match(price_str):
            # Extract the referenced address from "Inclus dans le contrat de ADDR"
            m = re.search(r"\bde\b\s+(.+?)(?:\s*\n|$)", price_str, re.I)
            ref_line = m.group(1).strip() if m else price_str.split("\n")[0]
            bundled_rows.append({
                "building_id": building_id,
                "addr": addr_raw,
                "ref_addr": ref_line,
                "row_num": row_num,
            })
            continue

        price, price_note = _extract_price(price_str)
        main_contracts.append({
            "building_id": building_id,
            "addr": addr_raw,
            "vendor_raw": vendor,
            "price": price,
            "price_note": price_note,
            "price_str": price_str,
            "approved": approved,
            "row_num": row_num,
        })

    return main_contracts, bundled_rows, unmatched


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

    all_contracts = []       # rows for service_contract
    all_bldg_links = []      # (contract_id_idx, building_id) — idx into all_contracts
    all_new_vendors = {}     # norm_key → nom
    all_unmatched = []
    all_bundled_miss = []

    for tab_name, category in TABS:
        ws = wb[tab_name]
        use_col8 = (tab_name == "Piétonnier")
        mains, bundled, unmatched = _parse_tab(ws, bldg_by_addr, use_col8_vendor=use_col8)
        all_unmatched.extend(f"[{tab_name}] {u}" for u in unmatched)

        # Index main contracts by building_id for bundled-row resolution
        main_by_bid = {c["building_id"]: i + len(all_contracts) for i, c in enumerate(mains)}

        for mc in mains:
            vendor_raw = mc["vendor_raw"]
            if not _is_real_vendor(vendor_raw):
                vendor_raw = ""
            raw_nk   = _norm_key(vendor_raw) if vendor_raw else ""
            canonical = _ALIASES.get(raw_nk, vendor_raw) if raw_nk else ""
            canon_nk  = _norm_key(canonical) if canonical else ""
            vid = vendor_by_norm.get(canon_nk) if canon_nk else None
            if canon_nk and vid is None:
                all_new_vendors[canon_nk] = canonical

            all_contracts.append({
                "category":    category,
                "building_id": mc["building_id"],
                "addr":        mc["addr"],
                "vendor_raw":  vendor_raw,
                "vendor_nk":   canon_nk,
                "vendor_canon": canonical,
                "price":       mc["price"],
                "price_note":  mc["price_note"],
                "price_str":   mc["price_str"],
                "approved":    mc["approved"],
                "tab":         tab_name,
                "row_num":     mc["row_num"],
            })
            all_bldg_links.append((len(all_contracts) - 1, mc["building_id"]))

        # Resolve bundled rows: match ref_addr → main contract
        for br in bundled:
            ref_bid, _ = _match(br["ref_addr"], bldg_by_addr)
            if ref_bid is not None and ref_bid in main_by_bid:
                all_bldg_links.append((main_by_bid[ref_bid], br["building_id"]))
            else:
                all_bundled_miss.append(
                    f"[{tab_name}] {_addr_first_line(br['addr'])!r} → ref {br['ref_addr']!r} unresolved"
                )

    wb.close()

    # ── Dry run report
    approved = [c for c in all_contracts if c["approved"]]
    not_approved = [c for c in all_contracts if not c["approved"]]
    price_ok = [c for c in approved if c["price"] is not None]
    price_miss = [c for c in approved if c["price"] is None]

    print(f"\n=== ingest_snow_contracts dry run ===")
    print(f"Tabs: Stationnement (snow_parking) + Piétonnier (snow_pedestrian)")
    print(f"Main contract rows: {len(all_contracts)}")
    print(f"  Validée/approved: {len(approved)}")
    print(f"  Not approved (skipped): {len(not_approved)}")
    print(f"  Approved with price:    {len(price_ok)}")
    print(f"  Approved, price missing:{len(price_miss)}")
    print(f"Building links total: {len(all_bldg_links)}")
    print(f"New vendors to add: {len(all_new_vendors)}")
    for nk, nom in sorted(all_new_vendors.items(), key=lambda x: x[1]):
        print(f"  {nom!r}")
    print(f"Unmatched buildings: {len(all_unmatched)}")
    for u in all_unmatched[:10]:
        print(f"  {u}")
    if len(all_unmatched) > 10:
        print(f"  ... +{len(all_unmatched)-10} more")
    print(f"Bundled rows with unresolved parent: {len(all_bundled_miss)}")
    for m in all_bundled_miss[:5]:
        print(f"  {m}")

    print("\n--- 10 price extraction samples (approved rows) ---")
    for c in approved[:10]:
        addr_line = _addr_first_line(c["addr"])[:40]
        price_disp = f"${c['price']:.2f} ({c['price_note']})" if c["price"] else f"NONE ({c['price_note']})"
        print(f"  [{c['tab']}] {addr_line!r}")
        print(f"    vendor: {c['vendor_raw'][:50]!r}")
        print(f"    price:  {price_disp}  full: {c['price_str'][:80]!r}")

    if dry_run:
        print("\nDRY RUN — pass --write to commit.")
        return

    # ── Write
    conn = get_conn()
    try:
        cur = conn.cursor()
        # Re-fetch offsets
        cur.execute("SELECT vendor_id, nom FROM vendor_contact")
        vendor_by_norm = {_norm_key(nom): vid for vid, nom in cur.fetchall()}
        cur.execute("SELECT COALESCE(MAX(contract_id), 0) FROM service_contract")
        contract_start = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        # Insert new vendors (canonical names only — aliases already collapsed above)
        cur.execute("SELECT COALESCE(MAX(vendor_id), 0) FROM vendor_contact")
        vid_start = cur.fetchone()[0]
        for i, (nk, nom) in enumerate(all_new_vendors.items()):
            new_vid = vid_start + i + 1
            cur.execute("INSERT INTO vendor_contact (vendor_id, nom) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (new_vid, nom))
            vendor_by_norm[nk] = new_vid

        # Insert approved contracts (vendor_id is nullable — write even when vendor is blank)
        contract_rows = []
        contract_id_map = {}  # idx → contract_id
        for i, c in enumerate(all_contracts):
            if not c["approved"]:
                continue
            vid   = vendor_by_norm.get(c["vendor_nk"]) if c["vendor_nk"] else None
            notes = c["price_str"][:1000] if c["price_str"] else None
            if vid is None and c.get("vendor_canon"):
                notes = f"[vendor unmatched: {c['vendor_canon']!r}] " + (notes or "")
            cid = contract_start + len(contract_rows) + 1
            contract_rows.append((
                cid, vid, c["category"],
                None, None,  # term_start, term_end — not in spreadsheet
                c["price"],
                False,  # renews
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

        # Insert building links
        bldg_link_rows = []
        for idx, bid in all_bldg_links:
            cid = contract_id_map.get(idx)
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
        for i, c in enumerate(all_contracts):
            cid = contract_id_map.get(i)
            if not cid:
                continue
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract", str(cid), "cost",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, c["tab"],
                c["row_num"], 5, c["price_str"][:2000] if c["price_str"] else None,
                str(c["price"]) if c["price"] else None, None,
            ))
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract", str(cid), "vendor_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, c["tab"],
                c["row_num"], 4, c["vendor_raw"], str(vendor_by_norm.get(c["vendor_nk"])), None,
            ))

        for idx, bid in all_bldg_links:
            cid = contract_id_map.get(idx)
            if not cid:
                continue
            c = all_contracts[idx]
            composite_pk = f"{cid},{bid}"
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract_building", composite_pk, "building_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, c["tab"],
                c["row_num"], 0, None, str(bid), None,
            ))
            prov_rows.append((
                prov_offset + len(prov_rows) + 1,
                "service_contract_building", composite_pk, "contract_id",
                "spreadsheet", _SRC_DRIVE_ID, _SRC_FILE, c["tab"],
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
