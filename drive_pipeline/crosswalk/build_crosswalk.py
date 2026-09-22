"""
build_crosswalk.py — Phase 0 building crosswalk.

Sources (authoritative):
  - Fiches Techniques ADDRESSES (drive_pipeline/fiches_techniques/map.py)
  - Master Rent Roll Google Sheet (all sheets via Sheets API)

Run from repo root:  uv run drive_pipeline/crosswalk/build_crosswalk.py

Outputs (dry run only — review before finalising):
  - prints summary to stdout
  - writes building_crosswalk.py, unmatched_fiches_techniques.py,
    unmatched_master_rent_roll.py in this package directory
"""

import io
import re
import unicodedata
import warnings
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import openpyxl

from drive_pipeline.fiches_techniques.map import ADDRESSES

ROOT = Path(__file__).parents[2]
load_dotenv(ROOT / ".env")

MASTER_RENT_ROLL_ID = "1wfGj7Bjzb08AyaOk5zzlnsvqzAcfPA66"

# ── normalisation ────────────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )

def normalise(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = _strip_accents(s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ── Drive API (xlsx download) ─────────────────────────────────────────────────

def _drive_service():
    creds = Credentials.from_authorized_user_file(
        str(ROOT / "token.json"),
        ["https://www.googleapis.com/auth/drive"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

def fetch_all_sheets(file_id: str) -> dict[str, list[list]]:
    """Download xlsx from Drive, return {sheet_name: [[row_values], ...]}."""
    svc = _drive_service()
    buf = io.BytesIO()
    req = svc.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(buf, data_only=True)

    result = {}
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            # Skip entirely blank rows
            if any(c.strip() for c in cells):
                rows.append(cells)
        result[ws.title] = rows
    return result

# ── Master Rent Roll parsing ──────────────────────────────────────────────────

# Oricom code pattern: e.g. "0125", "A002", sometimes embedded in header like "Bastien - 0125"
_ORICOM_RE = re.compile(r'\b([A-Z]?\d{3,4})\b')

# Civic number in MRR header, e.g. "1580" or "405-415"
_CIVIC_RE = re.compile(r'\b(\d{2,5}(?:-\d{2,5})?)\b')

def _extract_oricom(header: str) -> str | None:
    """Return Oricom-style code (4-digit number or A+digits) from a header string."""
    for m in _ORICOM_RE.finditer(header):
        code = m.group(1)
        # Prefer pure 4-digit codes; skip years and obvious non-codes
        if len(code) == 4 and code.isdigit() and not (1900 <= int(code) <= 2099):
            return code
        if re.match(r'^[A-Z]\d{3}$', code):
            return code
    return None

def _parse_mrr_building_block(sheet_title: str, rows: list[list]) -> dict | None:
    """
    Try to extract building identity from a sheet.
    MRR structure: first non-empty row(s) contain the building name/header.
    Returns dict or None if sheet looks like a non-building sheet (index, summary, etc.).
    """
    # Collect first few non-empty cell values to find the header
    header_candidates = []
    unit_count = None

    for row in rows[:15]:
        for cell in row:
            val = str(cell).strip() if cell else ""
            if val and len(val) > 2:
                header_candidates.append(val)
                break  # first non-empty cell per row

    if not header_candidates:
        return None

    # First candidate is the building name/header
    raw_header = header_candidates[0]

    # Skip obvious non-building sheets
    skip_keywords = ["index", "sommaire", "summary", "total", "tableau",
                     "liste", "feuille", "récapitulatif"]
    if any(kw in raw_header.lower() for kw in skip_keywords):
        return None

    oricom_code = _extract_oricom(raw_header)

    # Try to find a civic number in the header (if MRR uses address-style names)
    civic_in_header = None
    for m in _CIVIC_RE.finditer(raw_header):
        candidate = m.group(1)
        # Skip years
        if candidate.isdigit() and 1900 <= int(candidate) <= 2099:
            continue
        civic_in_header = candidate
        break

    # Look for unit count — scan first 30 rows for "logement" / "unit" / "apt" labels
    for row in rows[:50]:
        if len(row) >= 2:
            label = str(row[0]).lower() if row[0] else ""
            val   = str(row[1]).strip() if len(row) > 1 else ""
            if any(kw in label for kw in ["logement", "unit", "apt", "suite"]):
                try:
                    unit_count = int(re.search(r'\d+', val).group())
                except (AttributeError, ValueError):
                    pass

    return {
        "sheet_title":   sheet_title,
        "raw_header":    raw_header,
        "oricom_code":   oricom_code,
        "civic_in_header": civic_in_header,
        "unit_count":    unit_count,
    }

def parse_mrr(all_sheets: dict[str, list[list]]) -> list[dict]:
    buildings = []
    for title, rows in all_sheets.items():
        parsed = _parse_mrr_building_block(title, rows)
        if parsed:
            buildings.append(parsed)
    return buildings

# ── Matching ──────────────────────────────────────────────────────────────────

def _norm_street(s: str) -> str:
    """Normalise a street name for comparison."""
    s = normalise(s)
    # Expand common abbreviations that appear in either source
    s = re.sub(r'\bst\b\.?', 'saint', s)
    s = re.sub(r'\bave?\b\.?', 'avenue', s)
    s = re.sub(r'\brd\b\.?', 'road', s)
    s = re.sub(r'\bchemin\b', 'road', s)   # chemin ≈ road contextually
    return s.strip()

def _civic_overlap(a: str | None, b: str | None) -> bool:
    """True if the two civic strings share at least one numeric component."""
    if not a or not b:
        return False
    a_nums = set(re.findall(r'\d+', a))
    b_nums = set(re.findall(r'\d+', b))
    return bool(a_nums & b_nums)

def match_buildings(ft_addresses: list[dict], mrr_buildings: list[dict]) -> tuple[list, list, list]:
    """
    Returns (matched, unmatched_ft, unmatched_mrr).
    matched: list of crosswalk records.
    """
    matched = []
    used_mrr = set()

    for ft in ft_addresses:
        ft_street_norm = _norm_street(ft["street"])
        ft_civic = ft["civic_number"]

        best = None
        best_method = None

        for i, mrr in enumerate(mrr_buildings):
            if i in used_mrr:
                continue

            # Build searchable text from MRR record
            mrr_text = normalise(mrr["raw_header"] + " " + mrr["sheet_title"])
            mrr_civic = mrr.get("civic_in_header")

            # Method 1: street name appears in MRR header AND civic overlaps
            if ft_street_norm and ft_street_norm in mrr_text:
                if _civic_overlap(ft_civic, mrr_civic) or _civic_overlap(ft_civic, mrr["raw_header"]):
                    best = i
                    best_method = "exact_street_civic"
                    break

            # Method 2: street name appears in MRR header (no civic required — single match wins)
            if ft_street_norm and ft_street_norm in mrr_text:
                if best is None:
                    best = i
                    best_method = "street_only"
                elif best_method == "street_only":
                    # Ambiguous — multiple MRR rows match this street, don't pick
                    best = None
                    best_method = "ambiguous"

        if best is not None and best_method != "ambiguous":
            used_mrr.add(best)
            matched.append({
                "ft_street":      ft["street"],
                "ft_civic":       ft["civic_number"],
                "ft_city":        ft["city"],
                "ft_english_name": ft["english_name"],
                "ft_subfolder":   ft["subfolder"],
                "mrr_sheet_title": mrr_buildings[best]["sheet_title"],
                "mrr_raw_header": mrr_buildings[best]["raw_header"],
                "mrr_oricom_code": mrr_buildings[best]["oricom_code"],
                "mrr_unit_count": mrr_buildings[best]["unit_count"],
                "match_method":   best_method,
            })
        else:
            matched.append({
                "ft_street":      ft["street"],
                "ft_civic":       ft["civic_number"],
                "ft_city":        ft["city"],
                "ft_english_name": ft["english_name"],
                "ft_subfolder":   ft["subfolder"],
                "mrr_sheet_title": None,
                "mrr_raw_header": None,
                "mrr_oricom_code": None,
                "mrr_unit_count": None,
                "match_method":   "unmatched_ft",
            })

    unmatched_ft = [r for r in matched if r["match_method"] == "unmatched_ft"]
    matched_only = [r for r in matched if r["match_method"] != "unmatched_ft"]
    unmatched_mrr = [mrr for i, mrr in enumerate(mrr_buildings) if i not in used_mrr]

    return matched_only, unmatched_ft, unmatched_mrr

# ── Output writers ────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent

def _repr_val(v):
    if v is None:
        return "None"
    if isinstance(v, int):
        return str(v)
    return repr(v)

def write_crosswalk(matched: list[dict]):
    lines = [
        "# building_crosswalk.py — DRY RUN output, not yet final.",
        "# Review unmatched_*.py files before treating this as authoritative.",
        "# crosswalk_id will become building_id once ingestion starts.",
        "",
        "BUILDING_CROSSWALK = [",
    ]
    for i, r in enumerate(matched, 1):
        lines.append(f"    {{")
        lines.append(f"        'crosswalk_id':    {i},")
        lines.append(f"        'ft_street':       {repr(r['ft_street'])},")
        lines.append(f"        'ft_civic':        {repr(r['ft_civic'])},")
        lines.append(f"        'ft_city':         {repr(r['ft_city'])},")
        lines.append(f"        'ft_english_name': {repr(r['ft_english_name'])},")
        lines.append(f"        'mrr_sheet_title': {_repr_val(r['mrr_sheet_title'])},")
        lines.append(f"        'mrr_raw_header':  {_repr_val(r['mrr_raw_header'])},")
        lines.append(f"        'mrr_oricom_code': {_repr_val(r['mrr_oricom_code'])},")
        lines.append(f"        'mrr_unit_count':  {_repr_val(r['mrr_unit_count'])},")
        lines.append(f"        'match_method':    {repr(r['match_method'])},")
        lines.append(f"    }},")
    lines.append("]")
    (OUT_DIR / "building_crosswalk.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_unmatched_ft(unmatched: list[dict]):
    lines = [
        "# unmatched_fiches_techniques.py — FT addresses with no MRR match.",
        "# Review each entry; manual matching or exclusion needed.",
        "",
        "UNMATCHED_FT = [",
    ]
    for r in unmatched:
        lines.append(f"    {{'ft_street': {repr(r['ft_street'])}, 'ft_civic': {repr(r['ft_civic'])}, 'ft_city': {repr(r['ft_city'])}, 'ft_english_name': {repr(r['ft_english_name'])}}},")
    lines.append("]")
    (OUT_DIR / "unmatched_fiches_techniques.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_unmatched_mrr(unmatched: list[dict]):
    lines = [
        "# unmatched_master_rent_roll.py — MRR buildings with no FT match.",
        "# Review each entry; manual matching or exclusion needed.",
        "",
        "UNMATCHED_MRR = [",
    ]
    for r in unmatched:
        lines.append(f"    {{'sheet_title': {repr(r['sheet_title'])}, 'raw_header': {repr(r['raw_header'])}, 'oricom_code': {repr(r['oricom_code'])}, 'unit_count': {repr(r['unit_count'])}}},")
    lines.append("]")
    (OUT_DIR / "unmatched_master_rent_roll.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Fetching Master Rent Roll (all sheets)...")
    all_sheets = fetch_all_sheets(MASTER_RENT_ROLL_ID)
    print(f"  {len(all_sheets)} sheets found: {list(all_sheets)[:5]}{'...' if len(all_sheets) > 5 else ''}")

    print("Parsing MRR building blocks...")
    mrr_buildings = parse_mrr(all_sheets)
    print(f"  {len(mrr_buildings)} building records extracted")

    print(f"FT addresses: {len(ADDRESSES)}")

    print("Matching...")
    matched, unmatched_ft, unmatched_mrr = match_buildings(ADDRESSES, mrr_buildings)

    # ── summary ──
    exact = sum(1 for r in matched if r["match_method"] == "exact_street_civic")
    street_only = sum(1 for r in matched if r["match_method"] == "street_only")
    print(f"\n{'='*60}")
    print(f"DRY RUN RESULTS")
    print(f"{'='*60}")
    print(f"  FT total:              {len(ADDRESSES)}")
    print(f"  MRR buildings total:   {len(mrr_buildings)}")
    print(f"  Matched (exact):       {exact}")
    print(f"  Matched (street only): {street_only}")
    print(f"  Unmatched FT:          {len(unmatched_ft)}")
    print(f"  Unmatched MRR:         {len(unmatched_mrr)}")

    print(f"\n── MRR SHEET TITLES (all {len(all_sheets)}) ──")
    for t in all_sheets:
        print(f"  {t!r}")

    print(f"\n── MRR PARSED BUILDINGS ({len(mrr_buildings)}) ──")
    for b in mrr_buildings:
        print(f"  sheet={b['sheet_title']!r}  header={b['raw_header']!r}  oricom={b['oricom_code']}  civic={b['civic_in_header']}  units={b['unit_count']}")

    print(f"\n── MATCHED ({len(matched)}) ──")
    for r in matched:
        print(f"  [{r['match_method']}]  FT: {r['ft_civic']} {r['ft_street']}  →  MRR: {r['mrr_raw_header']!r}")

    print(f"\n── UNMATCHED FT ({len(unmatched_ft)}) ──")
    for r in unmatched_ft:
        print(f"  {r['ft_civic']} {r['ft_street']}, {r['ft_city']}  ({r['ft_english_name']!r})")

    print(f"\n── UNMATCHED MRR ({len(unmatched_mrr)}) ──")
    for b in unmatched_mrr:
        print(f"  sheet={b['sheet_title']!r}  header={b['raw_header']!r}  oricom={b['oricom_code']}")

    # Write output files
    write_crosswalk(matched)
    write_unmatched_ft(unmatched_ft)
    write_unmatched_mrr(unmatched_mrr)
    print(f"\nWrote: building_crosswalk.py, unmatched_fiches_techniques.py, unmatched_master_rent_roll.py")
    print("DRY RUN COMPLETE — review unmatched lists before treating crosswalk as final.")

if __name__ == "__main__":
    main()
