"""
build_crosswalk.py — Phase 0 building crosswalk.

Sources (authoritative):
  - Fiches Techniques ADDRESSES (drive_pipeline/fiches_techniques/map.py)
  - Master Rent Roll Google Sheet, Drive ID 1wfGj7Bjzb08AyaOk5zzlnsvqzAcfPA66 (xlsx)

MRR structure (confirmed by inspection):
  - 31 sheets total; first 9 are aggregate/summary (skipped)
  - 22 building project sheets; each sheet may cover multiple address buildings
  - Key column: "Unique Building Name" (col B) = "{civic} {street_name}" per building
  - Key column: "Unique Project Name" (col A) = project-level grouping name
  - One sheet can contain multiple distinct buildings (e.g. Commandeurs + Charbonnier + Ramoneur)

Run from repo root:  uv run python -m drive_pipeline.crosswalk.build_crosswalk

Outputs:
  - building_crosswalk.py         (matched records)
  - unmatched_fiches_techniques.py
  - unmatched_master_rent_roll.py
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

# Aggregate sheets to skip — not building data
AGGREGATE_SHEETS = {
    "Rent roll", "Revenus commerciaux", "Unités du Rent roll",
    "Dépôts locataires", "Rent roll format évaluateur",
    "Copie de Rent roll format évalu", "Rent roll format SCHL",
    "Revenus potentiels stationnemen", "Revenus potentiels rangements",
}

# ── normalisation ─────────────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )

# Street type suffixes to strip from both sides before comparison
_SUFFIX_RE = re.compile(
    r'\b(blvd|boulevard|boul|street|st\.?|ave\.?|avenue|lane|road|rd\.?|'
    r'rue|chemin|ch\.?|place|pl\.?|court|ct\.?|drive|dr\.?)$',
    re.IGNORECASE,
)

def _norm_street(s: str) -> str:
    """Normalise for street-name comparison: accents, case, hyphens, suffixes.

    Handles French MRR entries like "rue du Périgord" matching English FT entries
    like "Perigord Street" by stripping leading street-type words and articles.
    Stored values are never altered — this is comparison-only.
    """
    s = _strip_accents(s.lower())
    # Expand common abbreviations
    s = re.sub(r'\bste\b\.?', 'sainte', s)
    s = re.sub(r'\bst\b\.?(?!e)', 'saint', s)   # st but not ste (already handled)
    # Strip trailing type suffix
    s = _SUFFIX_RE.sub('', s).strip()
    # Strip leading French street-type prefix (MRR entries often start with "rue")
    s = re.sub(r'^(rue|avenue|av\.?|boul(?:evard)?|chemin)\s+', '', s)
    # Strip leading French articles / prepositions that follow the street type
    s = re.sub(r'^(du|de la|des|de l|de|le|la|les)\s+', '', s)
    # Collapse hyphens and whitespace uniformly
    s = re.sub(r'[-\s]+', ' ', s).strip()
    return s

def _civic_nums(civic: str | None) -> set[str]:
    """Extract all digit sequences from a civic string."""
    if not civic:
        return set()
    return set(re.findall(r'\d+', civic))

def _civic_overlap(a: str | None, b: str | None) -> bool:
    return bool(_civic_nums(a) & _civic_nums(b))

# ── Drive download ────────────────────────────────────────────────────────────

def _drive_service():
    creds = Credentials.from_authorized_user_file(
        str(ROOT / "token.json"),
        ["https://www.googleapis.com/auth/drive"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

def download_xlsx(file_id: str) -> openpyxl.Workbook:
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
        return openpyxl.load_workbook(buf, data_only=True)

# ── MRR parsing ───────────────────────────────────────────────────────────────

_BUILDING_NAME_RE = re.compile(
    r'^(\d[\d\-]*(?:\s+a\s+\d[\d\-]*)?)(?:\s*[-–]\s*|\s+)(.+)$'
)

def _parse_building_name(name: str) -> tuple[str | None, str | None]:
    """
    Parse "{civic_or_range} {street}" from MRR 'Unique Building Name' values.
    Handles: "1897 Bastien", "4837-4847 Saint-Georges", "2 a 36 Archer",
             "10943-10945-10947 Wilfrid-Caron", "209 a 243 Commandeurs".
    Returns (civic_str, street_str) or (None, None) if no civic prefix found.
    """
    name = name.strip()
    m = _BUILDING_NAME_RE.match(name)
    if m:
        civic = re.sub(r'\s+a\s+', '-', m.group(1).strip())
        street = m.group(2).strip()
        return civic, street
    return None, None

def parse_mrr_buildings(wb: openpyxl.Workbook) -> list[dict]:
    """
    Extract one record per unique building address from MRR workbook.
    Scans 'Unique Building Name' (col B) of each non-aggregate sheet.
    """
    seen_names: set[str] = set()
    buildings: list[dict] = []

    for ws in wb.worksheets:
        if ws.title in AGGREGATE_SHEETS:
            continue

        col_b_header = None
        project_name_col = None

        for row_idx, row in enumerate(ws.iter_rows(min_row=1, values_only=True), 1):
            cells = [str(c).strip() if c is not None else "" for c in row]
            if row_idx == 1:
                # Detect header row: find "Unique Building Name" col
                for i, h in enumerate(cells):
                    if "building name" in h.lower() or "nom de l'immeuble" in h.lower():
                        col_b_header = i
                    if "project name" in h.lower() or "nom du projet" in h.lower():
                        project_name_col = i
                continue

            if col_b_header is None:
                continue

            bname = cells[col_b_header] if col_b_header < len(cells) else ""
            pname = cells[project_name_col] if (project_name_col is not None and project_name_col < len(cells)) else ""

            if not bname or bname in seen_names:
                continue
            seen_names.add(bname)

            civic, street = _parse_building_name(bname)

            buildings.append({
                "sheet_title":    ws.title,
                "project_name":   pname,
                "building_name":  bname,
                "civic":          civic,
                "street":         street,
                "street_norm":    _norm_street(street) if street else None,
            })

    return buildings

# ── Matching ──────────────────────────────────────────────────────────────────

def match_crosswalk(
    ft_addresses: list[dict],
    mrr_buildings: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Match FT addresses against MRR buildings in two explicit passes.

    PASS 1 (exact): street_norm + civic_overlap across the ENTIRE FT dataset
    before any fallback tier fires. This prevents a FT entry that fails the
    civic check from consuming via fallback an MRR candidate that a later FT
    entry would have matched exactly.

    PASS 2 (fallback): street_only for remaining unmatched FT entries, only
    after Pass 1 has finished for all FT entries.

    Returns (matched, unmatched_ft, unmatched_mrr).
    """
    from collections import defaultdict

    used_mrr: set[int] = set()

    # Build lookup: street_norm → [(index, mrr_record), ...]
    mrr_by_street: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, mrr in enumerate(mrr_buildings):
        if mrr["street_norm"]:
            mrr_by_street[mrr["street_norm"]].append((i, mrr))

    matched: list[dict] = []
    pass1_misses: list[dict] = []   # FT entries that didn't get an exact match

    # ── Pass 1: exact (street_norm + civic_overlap) across all FT ────────────
    for ft in ft_addresses:
        ft_street_norm = _norm_street(ft["street"])
        ft_civic = ft["civic_number"]
        candidates = mrr_by_street.get(ft_street_norm, [])

        found = None
        for i, mrr in candidates:
            if i in used_mrr:
                continue
            if _civic_overlap(ft_civic, mrr["civic"]):
                used_mrr.add(i)
                found = _make_match(ft, mrr, "exact_street_civic")
                break

        if found:
            matched.append(found)
        else:
            pass1_misses.append(ft)

    # ── Pass 2: fallback tiers for everything that missed Pass 1 ─────────────
    unmatched_ft: list[dict] = []
    for ft in pass1_misses:
        ft_street_norm = _norm_street(ft["street"])
        candidates = mrr_by_street.get(ft_street_norm, [])
        fresh = [(i, m) for i, m in candidates if i not in used_mrr]

        if len(fresh) == 1:
            i, mrr = fresh[0]
            used_mrr.add(i)
            matched.append(_make_match(ft, mrr, "street_only_unambiguous"))
        elif len(fresh) > 1:
            # Multiple MRR candidates remain — cannot auto-assign
            matched.append({
                **_ft_fields(ft),
                **{k: None for k in ("mrr_sheet_title", "mrr_project_name",
                                     "mrr_building_name", "mrr_civic", "mrr_street")},
                "match_method": "review_needed_ambiguous",
            })
        else:
            unmatched_ft.append(ft)

    unmatched_mrr = [m for i, m in enumerate(mrr_buildings) if i not in used_mrr]
    return matched, unmatched_ft, unmatched_mrr

def _ft_fields(ft: dict) -> dict:
    return {
        "ft_street":       ft["street"],
        "ft_civic":        ft["civic_number"],
        "ft_city":         ft["city"],
        "ft_english_name": ft["english_name"],
        "ft_subfolder":    ft["subfolder"],
    }

def _make_match(ft: dict, mrr: dict, method: str) -> dict:
    return {
        **_ft_fields(ft),
        "mrr_sheet_title":   mrr["sheet_title"],
        "mrr_project_name":  mrr["project_name"],
        "mrr_building_name": mrr["building_name"],
        "mrr_civic":         mrr["civic"],
        "mrr_street":        mrr["street"],
        "match_method":      method,
    }

# ── Output writers ────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent

def _pv(v):
    return "None" if v is None else repr(v)

def write_crosswalk(matched: list[dict]) -> None:
    lines = [
        "# building_crosswalk.py — DRY RUN output. Review unmatched_*.py before finalising.",
        "# crosswalk_id will become building_id once ingestion starts.",
        "",
        "BUILDING_CROSSWALK = [",
    ]
    for cid, r in enumerate(matched, 1):
        lines += [
            "    {",
            f"        'crosswalk_id':      {cid},",
            f"        'ft_street':         {_pv(r['ft_street'])},",
            f"        'ft_civic':          {_pv(r['ft_civic'])},",
            f"        'ft_city':           {_pv(r['ft_city'])},",
            f"        'ft_english_name':   {_pv(r['ft_english_name'])},",
            f"        'mrr_sheet_title':   {_pv(r['mrr_sheet_title'])},",
            f"        'mrr_project_name':  {_pv(r['mrr_project_name'])},",
            f"        'mrr_building_name': {_pv(r['mrr_building_name'])},",
            f"        'mrr_civic':         {_pv(r['mrr_civic'])},",
            f"        'mrr_street':        {_pv(r['mrr_street'])},",
            f"        'match_method':      {_pv(r['match_method'])},",
            "    },",
        ]
    lines.append("]")
    (OUT_DIR / "building_crosswalk.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_unmatched_ft(rows: list[dict]) -> None:
    lines = [
        "# unmatched_fiches_techniques.py — FT addresses with no MRR match.",
        "# Review before crosswalk is considered final.",
        "",
        "UNMATCHED_FT = [",
    ]
    for r in rows:
        lines.append(
            f"    {{'ft_street': {repr(r['street'])}, 'ft_civic': {repr(r['civic_number'])}, "
            f"'ft_city': {repr(r['city'])}, 'ft_english_name': {repr(r['english_name'])}}},"
        )
    lines.append("]")
    (OUT_DIR / "unmatched_fiches_techniques.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_unmatched_mrr(rows: list[dict]) -> None:
    lines = [
        "# unmatched_master_rent_roll.py — MRR buildings with no FT match.",
        "# Review before crosswalk is considered final.",
        "",
        "UNMATCHED_MRR = [",
    ]
    for r in rows:
        lines.append(
            f"    {{'sheet_title': {repr(r['sheet_title'])}, 'building_name': {repr(r['building_name'])}, "
            f"'civic': {repr(r['civic'])}, 'street': {repr(r['street'])}}},"
        )
    lines.append("]")
    (OUT_DIR / "unmatched_master_rent_roll.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Downloading Master Rent Roll...")
    wb = download_xlsx(MASTER_RENT_ROLL_ID)
    sheet_names = [ws.title for ws in wb.worksheets]
    print(f"  {len(sheet_names)} sheets, {sum(1 for s in sheet_names if s not in AGGREGATE_SHEETS)} building sheets")

    print("Parsing MRR buildings from 'Unique Building Name' column...")
    mrr_buildings = parse_mrr_buildings(wb)
    print(f"  {len(mrr_buildings)} unique building addresses extracted")

    print(f"FT addresses: {len(ADDRESSES)}")
    print("Matching...")
    matched, unmatched_ft, unmatched_mrr = match_crosswalk(ADDRESSES, mrr_buildings)

    # Breakdown by method
    exact = sum(1 for r in matched if r["match_method"] == "exact_street_civic")
    street_only = sum(1 for r in matched if r["match_method"] == "street_only_unambiguous")
    ambiguous = sum(1 for r in matched if r["match_method"] == "review_needed_ambiguous")

    print(f"\n{'='*65}")
    print("DRY RUN RESULTS")
    print(f"{'='*65}")
    print(f"  FT total:                   {len(ADDRESSES)}")
    print(f"  MRR unique buildings:       {len(mrr_buildings)}")
    print(f"  Matched — exact (str+civic):{exact:>4}")
    print(f"  Matched — street only:      {street_only:>4}")
    print(f"  Flagged — ambiguous:        {ambiguous:>4}")
    print(f"  Unmatched FT:               {len(unmatched_ft):>4}  (no MRR counterpart)")
    print(f"  Unmatched MRR:              {len(unmatched_mrr):>4}  (no FT counterpart)")

    print(f"\n── ALL MRR BUILDING NAMES EXTRACTED ({len(mrr_buildings)}) ──")
    for b in mrr_buildings:
        print(f"  sheet={b['sheet_title']!r:<38}  building={b['building_name']!r:<36}  "
              f"civic={b['civic']}  street_norm={b['street_norm']!r}")

    print(f"\n── MATCHED ({len(matched)}) ──")
    for r in matched:
        print(f"  [{r['match_method']}]")
        print(f"    FT:  {r['ft_civic']:>20}  {r['ft_street']}")
        print(f"    MRR: {r['mrr_civic'] or '':>20}  {r['mrr_building_name']!r}  (sheet: {r['mrr_sheet_title']!r})")

    print(f"\n── UNMATCHED FT ({len(unmatched_ft)}) ──")
    for r in unmatched_ft:
        print(f"  {r['civic_number']:>20}  {r['street']}, {r['city']}  ({r['english_name']!r})")

    print(f"\n── UNMATCHED MRR ({len(unmatched_mrr)}) ──")
    for b in unmatched_mrr:
        print(f"  sheet={b['sheet_title']!r:<38}  building={b['building_name']!r}")

    # Write output files
    all_non_unmatched = [r for r in matched if r["match_method"] != "review_needed_ambiguous"]
    ambiguous_as_unmatched = [
        {"street": r["ft_street"], "civic_number": r["ft_civic"],
         "city": r["ft_city"], "english_name": r["ft_english_name"]}
        for r in matched if r["match_method"] == "review_needed_ambiguous"
    ]

    write_crosswalk(all_non_unmatched)
    write_unmatched_ft(unmatched_ft + ambiguous_as_unmatched)
    write_unmatched_mrr(unmatched_mrr)
    print(f"\nWrote building_crosswalk.py ({len(all_non_unmatched)} records), "
          f"unmatched_fiches_techniques.py ({len(unmatched_ft) + len(ambiguous_as_unmatched)}), "
          f"unmatched_master_rent_roll.py ({len(unmatched_mrr)})")
    print("DRY RUN COMPLETE — review unmatched lists before treating crosswalk as final.")

if __name__ == "__main__":
    main()
