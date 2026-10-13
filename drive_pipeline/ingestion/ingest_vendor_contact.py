"""
ingest_vendor_contact.py — Dry-run and write ingestion of vendor_contact rows.

Sources:
  1. Hardcoded calendar-parser vendor codes
  2. Elevator_Contracts_EN.xlsx (Customer column)
  3. Boilers_EN.xlsx (Designated contractor column)
  4. Fire_Protection_EN.xlsx (gicleurs, CO2, current fire service columns)
  5. Plumber Search.xlsx (multi-line column headers)
  6. RENSEIGNEMENTS CONTACT IMPORTANTS… .xlsx (optional; skipped if absent)

Run:
    uv run python -m drive_pipeline.ingestion.ingest_vendor_contact                            # dry run
    uv run python -m drive_pipeline.ingestion.ingest_vendor_contact --write                    # write
    uv run python -m drive_pipeline.ingestion.ingest_vendor_contact --allow-missing-sources    # skip absent optional files instead of erroring
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.provenance import log_provenance, flush

# ── Constants ─────────────────────────────────────────────────────────────────

SOURCE_TYPE = "spreadsheet"
CALENDAR_SOURCE = "calendar_parser"

_RENSEIGNEMENTS_PATH = ROOT / "work/dryrun_maintenance/RENSEIGNEMENTS CONTACT IMPORTANTS IMMEUBLES ET EMPLOYÉS.xlsx"
_ELEV_PATH           = ROOT / "work/dryrun_maintenance/Elevator_Contracts_EN.xlsx"
_BOILERS_PATH        = ROOT / "work/dryrun_maintenance/Boilers_EN.xlsx"
_FIRE_PATH           = ROOT / "work/dryrun_maintenance/Fire_Protection_EN.xlsx"
_PLUMBER_PATH        = ROOT / "work/dryrun_maintenance/Plumber Search.xlsx"

# Confirmed vendors from live maintenance tickets (calendar parser codes)
_CALENDAR_VENDORS = [
    ("TK",                    "elevator_maintenance", None, "TK"),
    ("Ascenseur MAXI INC",    "elevator_maintenance", None, "MAXI"),
    ("Éric (extermination)",  "extermination",        None, "ERIC"),
    ("PDQ",                   "garage_door",          None, "PDQ"),
    ("ÉlectroDB",             "electrical",           None, "ÉlectroDB"),
    ("Boucher-Lortie",        "electrical",           None, "BoucherLortie"),  # électricité per secteurs-et-equipe
    ("Plomberie Fortin",      "plumbing",             None, "Fortin"),
    ("Wifi Québec",           "internet",             None, "WifiQuebec"),
    ("Coinamatic",            "laundry",              None, "Coinamatic"),
    ("Duclos",                "windows_doors",        None, "Duclos"),     # portes/fenêtres/vitres
    ("Davor",                 "appliances",           None, "Davor"),      # électroménagers
    ("4 Saisons",             "roofing",              None, "4Saisons"),   # toitures per secteurs-et-equipe
    ("Soluclim",              "hvac",                 None, "Soluclim"),
    ("EnviroConfort",         "hvac",                 None, "EnviroConfort"),
    ("Alarme Experts",        "fire_protection",      None, "AlarmeExpert"),
    ("H2Pro",                 "pool",                 None, "H2Pro"),      # piscines per secteurs-et-equipe
    ("Labrecque",             "flooring",             None, "Labrecque"),  # planchers
    ("Matrec",                "waste_management",     None, "Matrec"),
    ("Newtech",               "electrical",           None, "Newtech"),    # électricité, listed with Boucher Lortie
]

# Additional vendors confirmed in secteurs-et-equipe.md not present in any spreadsheet source
_EQUIPE_VENDORS = [
    ("Body Gym",         "gym_equipment",    None, "Body Gym"),
    ("JC Perreault",     "appliances",       None, "JC Perreault"),
    ("Émaillage Québec", "bath_refinishing", None, "Émaillage Québec"),
]

# Boilers contractor values that are building names or notes, not real vendors
_BOILERS_CONTRACTOR_SKIP = {"to be determined"}

# normalized key → canonical nom (richer form wins)
_ALIASES: dict[str, str] = {
    "maxi":                         "Ascenseur MAXI INC",
    "ascenseurmaxiinc":             "Ascenseur MAXI INC",
    "ascenseursmaxi":               "Ascenseur MAXI INC",
    "boucherlortie":                "Boucher-Lortie",
    "protek":                       "Y Pro-Tek",
    "yprotek":                      "Y Pro-Tek",
    "alarmeexpert":                 "Alarme Experts",
    "alarmeexperts":                "Alarme Experts",
    "groupealarmeexpert":           "Alarme Experts",
    "fortin":                       "Plomberie Fortin",
    "plomberiefortin":              "Plomberie Fortin",
    "eric":                         "Éric (extermination)",
    "ericextermination":            "Éric (extermination)",
    "ericnadeaugestionparasitaire": "Éric (extermination)",
    "quebecextermination":          "Québec Extermination",
    # Fire protection: French name in secteurs-et-equipe = English in Fire_Protection_EN
    "gicleursquebecois":            "Quebec Sprinklers",
    "quebecsprinklers":             "Quebec Sprinklers",
    "gicleurquebecois":             "Quebec Sprinklers",
    "unikgicleurs":                 "Quebec Sprinklers",
    "tkeascenseur":                 "TK",
    "thermosenergy":                "Thermo Énergie",
    "thermosenergie":               "Thermo Énergie",
    "telealarmeplus":               "Tele alarm plus",
    "toitures4saisons":             "4 Saisons",
    "emaillagequebec":              "Émaillage Québec",
    "enamelquebec":                 "Émaillage Québec",
    "electrodb":                    "ÉlectroDB",
    "enviroconfort":                "EnviroConfort",
    "kone":                         "KONE",
}

_PHONE_RE = re.compile(r"[\d]{3}[\s\-\.][\d]{3}[\s\-\.][\d]{4}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm_key(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _canonical(raw: str) -> str:
    nk = _norm_key(raw)
    return _ALIASES.get(nk, raw)


def _v(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _parse_plumber_header(cell_val: str) -> tuple[str, str | None]:
    """'Company Name\\nPhone\\n\\nemail' → (nom, phone|None)"""
    parts = [p.strip() for p in str(cell_val).split("\n") if p.strip()]
    nom = parts[0] if parts else str(cell_val).strip()
    phone = next((p for p in parts[1:] if _PHONE_RE.search(p)), None)
    return nom, phone


# ── Collection ────────────────────────────────────────────────────────────────

# Appearance = (nom, trade, telephone, source_file, source_tab, source_row, source_col, raw_value[, rich_notes])
Appearance = tuple

def _collect(allow_missing: bool = False) -> list[Appearance]:
    appearances: list[Appearance] = []

    # 1. Calendar parser codes
    for nom, trade, phone, code in _CALENDAR_VENDORS:
        appearances.append((nom, trade, phone,
                            "parse_calendar_requests.py", None, None,
                            "KNOWN_VENDOR_CODES or vendor_regex", code))

    # 1b. secteurs-et-equipe.md vendors not in any spreadsheet source
    for nom, trade, phone, label in _EQUIPE_VENDORS:
        appearances.append((nom, trade, phone,
                            "secteurs-et-equipe.md", None, None,
                            "Fournisseurs externes", label))

    # 2. Elevator contracts
    wb = openpyxl.load_workbook(str(_ELEV_PATH), read_only=True, data_only=True)
    ws = wb["Feuil1"]
    for sheet_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        raw = row[2] if len(row) > 2 else None
        v = _v(raw)
        if not v or "\n" in v or v.count(" ") > 5:  # skip empty and free-text/notes cells
            continue
        appearances.append((v, "elevator_maintenance", None,
                            "Elevator_Contracts_EN.xlsx", "Feuil1", sheet_row,
                            "Customer", raw))
    wb.close()

    # 3. Boilers
    wb = openpyxl.load_workbook(str(_BOILERS_PATH), read_only=True, data_only=True)
    ws = wb["Entretien - ChaudièresFournaise"]
    for sheet_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        raw = row[10] if len(row) > 10 else None
        v = _v(raw)
        if not v or v.lower() in _BOILERS_CONTRACTOR_SKIP or v.upper() == "N/A":
            continue
        appearances.append((v, "hvac", None,
                            "Boilers_EN.xlsx", "Entretien - ChaudièresFournaise",
                            sheet_row, "Designated contractor", raw))
    wb.close()

    # 4. Fire protection — 3 vendor columns
    wb = openpyxl.load_workbook(str(_FIRE_PATH), read_only=True, data_only=True)
    ws = wb["MASTER 1"]
    fire_cols = [(14, "Compagnie gicleurs"), (18, "Compagnie CO2"), (20, "Current fire service provider")]
    for sheet_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        for ci, col_name in fire_cols:
            raw = row[ci] if len(row) > ci else None
            v = _v(raw)
            if not v or v.upper() in ("N/A", "NA"):
                continue
            appearances.append((v, "fire_protection", None,
                                "Fire_Protection_EN.xlsx", "MASTER 1",
                                sheet_row, col_name, raw))
    wb.close()

    # 5. Plumber search — vendors in row-1 column headers
    wb = openpyxl.load_workbook(str(_PLUMBER_PATH), read_only=True, data_only=True)
    ws = wb["Feuille 1"]
    for col_idx, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1)), start=1):
        if not cell.value:
            continue
        nom, phone = _parse_plumber_header(cell.value)
        if not nom:
            continue
        appearances.append((nom, "plumbing", phone,
                            "Plumber Search.xlsx", "Feuille 1",
                            1, f"col_{col_idx} (header)", cell.value))
    wb.close()

    # 6. RENSEIGNEMENTS (authoritative vendor master list — required by default)
    if not _RENSEIGNEMENTS_PATH.exists():
        if allow_missing:
            print(f"WARNING: RENSEIGNEMENTS file not found at:\n  {_RENSEIGNEMENTS_PATH}\n  Skipping (--allow-missing-sources set).")
        else:
            raise FileNotFoundError(
                f"RENSEIGNEMENTS file not found:\n  {_RENSEIGNEMENTS_PATH}\n"
                "This file is the authoritative vendor master list. Without it the output\n"
                "covers only ~23% of expected vendors. Download it from Google Drive first,\n"
                "or pass --allow-missing-sources to override."
            )
    if _RENSEIGNEMENTS_PATH.exists():
        wb = openpyxl.load_workbook(str(_RENSEIGNEMENTS_PATH), read_only=True, data_only=True)
        if "Fournisseurs principaux" in wb.sheetnames:
            ws = wb["Fournisseurs principaux"]
            # Fixed layout: [0]=Nom [1]=Fonction [2]=Contact [3]=Tel1 [4]=Tel2 [5]=Courriel [6]=Notes
            for sheet_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                nom_raw = row[0] if len(row) > 0 else None
                v = _v(nom_raw)
                if not v:
                    continue
                trade_raw   = _v(row[1]) if len(row) > 1 else None
                phone_raw   = _v(row[3]) if len(row) > 3 else None
                ph2_raw     = _v(row[4]) if len(row) > 4 else None
                email_raw   = _v(row[5]) if len(row) > 5 else None
                notes_raw   = _v(row[6]) if len(row) > 6 else None
                contact_raw = _v(row[2]) if len(row) > 2 else None
                rich_parts = []
                if contact_raw: rich_parts.append(f"Contact: {contact_raw}")
                if ph2_raw:     rich_parts.append(f"Tel2: {ph2_raw}")
                if email_raw:   rich_parts.append(f"Email: {email_raw}")
                if notes_raw:   rich_parts.append(notes_raw)
                rich_notes = "; ".join(rich_parts) if rich_parts else None
                appearances.append((v, trade_raw or "unknown", phone_raw,
                                    _RENSEIGNEMENTS_PATH.name, "Fournisseurs principaux",
                                    sheet_row, "Nom", nom_raw, rich_notes))
        wb.close()

    return appearances


# ── Dedup ─────────────────────────────────────────────────────────────────────

def _dedupe(appearances: list[Appearance]):
    """
    Returns:
      vendors: list of (vendor_id, canonical_nom, trade, telephone, notes)
      prov_entries: list of (vendor_id, target_column, source_file, source_tab,
                             source_row, source_col, raw_value, ingested_value)
      cross_source: list of (canonical_nom, sources_str) for same vendor in 2+ files
    """
    # canonical_nom → {trade, telephone, sources: set[file], prov: list}
    data: dict[str, dict] = {}
    raw_count = 0

    for a in appearances:
        nom, trade, phone, src_file, src_tab, src_row, src_col, raw = a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]
        rich_notes = a[8] if len(a) > 8 else None
        raw_count += 1
        canon = _canonical(nom)
        if canon not in data:
            data[canon] = {"trade": "unknown", "telephone": None, "sources": set(), "prov": [], "rich_notes": None}
        d = data[canon]
        if trade and trade != "unknown" and d["trade"] == "unknown":
            d["trade"] = trade
        if phone and d["telephone"] is None:
            d["telephone"] = phone
        if rich_notes and not d["rich_notes"]:
            d["rich_notes"] = rich_notes
        d["sources"].add(src_file)
        d["prov"].append((src_file, src_tab, src_row, src_col, raw, canon))

    vendors = []
    prov_entries = []
    cross_source = []

    for vid, (canon, d) in enumerate(data.items(), start=1):
        src_list = ", ".join(sorted(d["sources"]))
        notes = d["rich_notes"] or f"Sources: {src_list}"
        vendors.append((vid, canon, d["trade"], d["telephone"], notes))

        for src_file, src_tab, src_row, src_col, raw, ingested in d["prov"]:
            prov_entries.append((vid, "nom", src_file, src_tab, src_row, src_col, raw, ingested))

        if len(d["sources"]) > 1:
            cross_source.append((canon, src_list))

    return vendors, prov_entries, cross_source, raw_count


# ── Run ───────────────────────────────────────────────────────────────────────

def run(dry_run: bool = True, allow_missing: bool = False) -> None:
    appearances = _collect(allow_missing=allow_missing)
    vendors, prov_entries, cross_source, raw_count = _dedupe(appearances)

    # ── source counts
    src_counts: dict[str, set] = defaultdict(set)
    src_raw: dict[str, int] = defaultdict(int)
    for nom, trade, phone, src_file, *_ in appearances:
        src_counts[src_file].add(nom)
        src_raw[src_file] += 1

    print("\n=== vendor_contact dry run ===")
    print("Source counts (raw appearances):")
    for src, cnt in sorted(src_raw.items()):
        uniq = len(src_counts[src])
        if cnt == uniq:
            print(f"  {src:<40} {cnt}")
        else:
            print(f"  {src:<40} {cnt} ({uniq} unique values)")
    if not _RENSEIGNEMENTS_PATH.exists():
        print(f"  {'RENSEIGNEMENTS':<40} SKIPPED (file not found)")
    print(f"  {'Total raw':<40} {raw_count}")

    print(f"\nDedup:")
    print(f"  {raw_count} raw → {len(vendors)} canonical vendors ({raw_count - len(vendors)} collapses)")
    if cross_source:
        print("  Cross-source matches:")
        for canon, srcs in cross_source:
            print(f"    {canon!r}: {srcs}")

    n_trade = sum(1 for _, _, t, _, _ in vendors if t and t != "unknown")
    n_phone = sum(1 for _, _, _, p, _ in vendors if p)
    print(f"\nField coverage:")
    print(f"  nom:       {len(vendors)}/{len(vendors)} (100%)")
    print(f"  trade:     {n_trade}/{len(vendors)} ({100*n_trade//len(vendors)}%)")
    print(f"  telephone: {n_phone}/{len(vendors)} ({100*n_phone//len(vendors)}%)")

    trade_counts: dict[str, int] = defaultdict(int)
    for _, _, t, _, _ in vendors:
        trade_counts[t or "unknown"] += 1
    print("\nVendors by trade:")
    for t, n in sorted(trade_counts.items()):
        print(f"  {t}: {n}")

    print("\nFull vendor list:")
    for vid, nom, trade, phone, _ in vendors:
        print(f"  [id={vid}] {nom!r} trade={trade} phone={phone!r}")

    if dry_run:
        print(f"\nDRY RUN — {len(vendors)} vendors, {len(prov_entries)} provenance rows. Pass --write to commit.")
        return

    # ── Write
    print(f"\nWriting {len(vendors)} vendors to Supabase…")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        execute_values(
            cur,
            "INSERT INTO vendor_contact (vendor_id, trade, nom, telephone, notes) VALUES %s",
            [(vid, trade, nom, phone, notes) for vid, nom, trade, phone, notes in vendors],
            page_size=2000,
        )

        all_prov = []
        for vid, target_col, src_file, src_tab, src_row, src_col, raw, ingested in prov_entries:
            all_prov.append((
                None,  # provenance_id assigned below
                "vendor_contact", vid, target_col,
                CALENDAR_SOURCE if src_file == "parse_calendar_requests.py" else SOURCE_TYPE,
                None, src_file, src_tab, src_row, src_col, raw, ingested, None,
            ))

        _CHUNK = 5000
        for start in range(0, len(all_prov), _CHUNK):
            chunk = all_prov[start:start + _CHUNK]
            execute_values(
                cur,
                """INSERT INTO data_provenance
                   (provenance_id, target_table, target_pk, target_column,
                    source_type, source_drive_id, source_file_name, source_tab,
                    source_row, source_column, raw_value, ingested_value, ingested_at)
                   VALUES %s""",
                [(prov_offset + start + i + 1,
                  r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12])
                 for i, r in enumerate(chunk)],
                page_size=5000,
            )

        conn.commit()
        print(f"Committed: {len(vendors)} vendor_contact rows, {len(all_prov)} provenance rows.")

        cur.execute("SELECT COUNT(*) FROM vendor_contact")
        print(f"vendor_contact total: {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(
        dry_run="--write" not in sys.argv,
        allow_missing="--allow-missing-sources" in sys.argv,
    )
