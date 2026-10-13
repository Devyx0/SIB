"""
ingest_building.py — DRY RUN: TF-anchored building ingestion with TF+FT merge.

Anchor   : TABLE_FONDAMENTALE (179 rows → building_id 1..179 in row order)
Sources  : TF direct columns + FT (.xlsx) where a file is matched
Precedence: TF wins on overlapping fields; FT fills gaps; raw_fiche_technique
            always stores the full FT blob regardless.
MRR      : Not an attribute source — project-name disagreements flagged only.
Do NOT write to Supabase.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_building
"""

import io
import re
import sys
import unicodedata
import warnings
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as _gapi_build
from googleapiclient.http import MediaIoBaseDownload
import openpyxl

from drive_pipeline.table_fondamentale.table_fondamentale import TABLE_FONDAMENTALE
from drive_pipeline.fiches_techniques.links import FICHES
from drive_pipeline.fiches_techniques.label_glossary import VARIANT_TO_CANONICAL
from drive_pipeline.crosswalk.building_crosswalk import BUILDING_CROSSWALK
from drive_pipeline.ingestion.provenance import log_provenance, flush

# ── Auth ──────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_service():
    creds = Credentials.from_authorized_user_file(str(ROOT / "token.json"), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return _gapi_build("drive", "v3", credentials=creds)


def _download_xlsx(service, file_id: str) -> io.BytesIO:
    buf = io.BytesIO()
    req = service.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf


# ── TF → FT matcher ───────────────────────────────────────────────────────────

_SFXS = re.compile(
    r"\b(blvd|boulevard|boul|street|st|ave|avenue|lane|road|rd|rue|"
    r"chemin|ch|place|pl|court|ct|drive|dr|west|est|ouest|sud|nord)\b",
    re.IGNORECASE,
)
_ORD_RE = re.compile(r"^\d{1,4}e$")  # canonical ordinal tokens: "4e", "48e", "49e"


def _nrm(s: str) -> str:
    s = "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"\bste\b", "sainte", s)
    s = re.sub(r"\bst\b", "saint", s)
    # Unify English and French ordinal markers so "49th" and "49e" both become "49e"
    s = re.sub(r"\b(\d+)(?:th|nd|rd|eme|ieme|ere)\b", r"\1e", s)
    s = _SFXS.sub(" ", s)
    s = re.sub(r"[!,()[\]]+", " ", s)
    return re.sub(r"[-\s/]+", " ", s).strip()


def _words(s: str) -> set[str]:
    return {w for w in s.split() if (len(w) >= 3 or _ORD_RE.match(w)) and not w.isdigit()}


def _digits(s: str) -> set[str]:
    return set(re.findall(r"\d+", s))


def _build_ft_index() -> dict[str, list]:
    """Index FICHES by normalised street words → [(fiche, ft_digits, ft_words), ...]."""
    idx: dict[str, list] = defaultdict(list)
    for fiche in FICHES:
        en = fiche["english_name"]
        street_part = en.split(",")[0] if "," in en else en
        nrm = _nrm(street_part)
        fw = _words(nrm)
        fd = _digits(en)
        for w in fw:
            idx[w].append((fiche, fd, fw))
    return idx


_FT_IDX = _build_ft_index()


def _match_tf_to_ft(tf_row: dict) -> list[dict]:
    """Return list of FT FICHES entries matching this TF row (may be empty)."""
    bn = tf_row.get("unique_building_name", "")
    # Strip unit-range parentheticals: "1175 Chamonix (1 a 26)" → "1175 Chamonix"
    bn_clean = re.sub(r"\([^)]*\)", "", bn).strip()
    tf_d = _digits(bn_clean)

    # Street part: after leading civic / range prefix
    m = re.match(r"^\d+\s+a\s+\d+\s+(.+)$", bn_clean)
    if m:
        street_part = m.group(1).strip()
    else:
        # Strip leading multi-civic prefix (e.g. "4825-4855-4875 ") but NOT the
        # ordinal street digit that follows (e.g. "4" in "4e Avenue").
        street_part = re.sub(r"^\d[\d\-]*\s+", "", bn_clean).strip()

    tf_w = _words(_nrm(street_part))

    seen: set[str] = set()
    results: list[dict] = []
    for w in tf_w:
        for fiche, fd, fw in _FT_IDX.get(w, []):
            key = fiche["english_name"]
            if key not in seen and tf_d & fd and tf_w & fw:
                seen.add(key)
                results.append(fiche)
    return results


# ── FT xlsx reader ────────────────────────────────────────────────────────────

_OUI_RE = re.compile(r"^\s*(oui|yes|true|1|x)\s*$", re.IGNORECASE)
_NON_RE = re.compile(r"^\s*(non|no|false|0|n/a|n\.?a\.?|-)\s*$", re.IGNORECASE)
_PAS_RE = re.compile(r"^\s*pas\s+de\b", re.IGNORECASE)
_AUCUN_RE = re.compile(r"^\s*aucun", re.IGNORECASE)


def _to_bool(raw) -> bool | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if _NON_RE.match(s) or _PAS_RE.match(s) or _AUCUN_RE.match(s):
        return False
    if _OUI_RE.match(s):
        return True
    return True  # non-empty, non-negative → presence implied


def _to_int_str(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return str(int(float(s)))
    except (ValueError, OverflowError):
        return s


def _read_ft_labels(buf: io.BytesIO) -> dict:
    """Parse FT xlsx → {canonical_french_label: {row, raw_label, raw_value}}."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(buf, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    result: dict = {}
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
        if not row:
            continue
        raw_label = row[0] if len(row) > 0 else None
        raw_value = row[1] if len(row) > 1 else None
        if raw_label is None:
            continue
        label_str = str(raw_label).strip()
        if not label_str:
            continue
        canonical = VARIANT_TO_CANONICAL.get(label_str) or \
                    VARIANT_TO_CANONICAL.get(label_str.rstrip(":").strip())
        if canonical and canonical not in result:
            result[canonical] = {"row": row_idx, "raw_label": label_str, "raw_value": raw_value}
    wb.close()
    return result


# ── Field maps ────────────────────────────────────────────────────────────────

# FT: DB column → ([canonical_labels_in_priority_order], type)
# Columns marked "overlap" share with TF; TF wins unless TF is None.
_FT_FIELD_MAP: dict[str, tuple[list[str], str]] = {
    "annee_construction": (["Année de construction"],                  "int_str"),  # overlap
    "nb_etages":          (["Nb d’étages", "Étages"],   "int_str"),  # overlap
    "nb_logements":       (["Nb de logements", "Logements"],           "int_str"),  # FT-only
    "ascenseur":          (["Ascenseur"],                              "bool"),     # overlap
    "piscine":            (["Piscine"],                                "bool"),     # overlap
    "sauna":              (["Sauna"],                                  "bool"),     # overlap
    "gym":                (["Gym"],                                    "bool"),     # overlap
    "chauffage":          (["Chauffage"],                              "str"),      # overlap
    "systeme_incendie":   (["Système incendie"],                  "bool"),     # FT-only
    "boite_a_cle_ext":    (["Boîte à clé (extérieure)"], "bool"),  # FT-only
    "boite_a_cle_int":    (["Boîte à clé (intérieure)"], "bool"),  # FT-only
}

# Columns that exist in both TF and FT (TF wins, FT fills if TF is None)
_OVERLAP_COLS = {"annee_construction", "nb_etages", "ascenseur", "piscine", "sauna", "gym", "chauffage"}

# Known TF data errors where FT should override. Two provenance rows per entry.
_TF_OVERRIDES: frozenset[tuple[int, str]] = frozenset({
    (150, "ascenseur"),  # 350 Ch Ste-Foy: TF has 0 elevators, FT confirms 2 mechanical
    (152, "ascenseur"),  # 117 Ste-Anne: TF has 0 elevators, FT confirms elevator vendor
})

# All DB columns in insertion order
_ALL_COLS = [
    # Identity
    "sib_territory", "unique_project_name", "quickbooks_address",
    "adresse", "ville",
    # Structure
    "furnished", "building_structure",
    "annee_construction", "nb_etages", "nb_logements",
    # Elevators
    "ascenseur", "nb_elevateurs", "num_service_elevators",
    # Connectivity/amenities (TF-only or FT-only)
    "internet",
    "piscine", "sauna", "gym",
    "terrasse_commune", "num_bbqs", "coworking_space", "reception_loft",
    # Heating
    "chauffage", "chauffage_details", "chauffe_eau",
    "individual_heat_pumps", "heat_pump_details",
    # FT-only safety/access
    "systeme_incendie", "boite_a_cle_ext", "boite_a_cle_int",
    # Blobs
    "raw_fiche_technique",
]


def _yn(v) -> bool | None:
    """Convert TF Yes/No string to bool."""
    if v is None:
        return None
    return _to_bool(str(v))


def _tf_fields(tf_row: dict) -> dict:
    """Map TF row → {db_col: normalised_value}. All columns; missing → None."""
    ne = tf_row.get("num_elevators") or 0
    return {
        "sib_territory":        tf_row.get("sib_territory"),
        "unique_project_name":  tf_row.get("unique_project_name"),
        "quickbooks_address":   tf_row.get("quickbooks_project_address"),
        "adresse":              tf_row.get("unique_building_name"),
        "ville":                None,  # populated from FT city below
        "furnished":            tf_row.get("furnished"),
        "building_structure":   tf_row.get("building_structure"),
        "annee_construction":   _to_int_str(tf_row.get("year_built")),
        "nb_etages":            _to_int_str(tf_row.get("num_floors")),
        "nb_logements":         None,  # FT-only
        "ascenseur":            True if ne > 0 else False,
        "nb_elevateurs":        ne,    # TF integer count, kept separate from bool ascenseur
        "num_service_elevators": tf_row.get("num_service_elevators"),
        "internet":             tf_row.get("internet"),
        "piscine":              _yn(tf_row.get("pool")),
        "sauna":                _yn(tf_row.get("sauna")),
        "gym":                  _yn(tf_row.get("fitness_room")),
        "terrasse_commune":     _yn(tf_row.get("common_terrace")),
        "num_bbqs":             tf_row.get("num_bbqs"),
        "coworking_space":      _yn(tf_row.get("coworking_space")),
        "reception_loft":       _yn(tf_row.get("reception_loft")),
        "individual_heat_pumps": _yn(tf_row.get("individual_heat_pumps")),
        "heat_pump_details":    tf_row.get("heat_pump_details"),
        "chauffage":            tf_row.get("heating_mode"),
        "chauffage_details":    tf_row.get("heating_details"),
        "chauffe_eau":          tf_row.get("hot_water_mode"),
        # FT-only columns — None until FT merge
        "systeme_incendie":     None,
        "boite_a_cle_ext":      None,
        "boite_a_cle_int":      None,
        "raw_fiche_technique":  None,
    }


def _ft_extract(ft_labels: dict) -> dict[str, tuple]:
    """
    Extract FT fields. Returns {db_col: (ingested_value, label_entry)}.
    Only columns with a non-None value are included.
    """
    result: dict[str, tuple] = {}
    claimed: set[str] = set()  # first canonical per DB col wins
    for col, (canonicals, typ) in _FT_FIELD_MAP.items():
        if col in claimed:
            continue
        for canon in canonicals:
            entry = ft_labels.get(canon)
            if entry is None:
                continue
            raw = entry["raw_value"]
            if typ == "bool":
                val = _to_bool(raw)
            elif typ == "int_str":
                val = _to_int_str(raw)
            else:
                val = str(raw).strip() if raw is not None else None
            if val is not None:
                result[col] = (val, entry)
                claimed.add(col)
                break
    return result


# ── Merge + provenance ────────────────────────────────────────────────────────

TF_FILE = "table_fondamentale.py"
LINKS_FILE = "links.py"


def _merge_and_log(
    building_id: int,
    tf_row: dict,
    tf: dict,
    ft_ext: dict,
    ft_fiche: dict | None,
    ft_labels: dict,
) -> tuple[dict, list[str], list[dict]]:
    """
    Merge tf + ft_ext into final record. TF wins on overlap.
    Logs provenance for every non-null field.
    Returns (merged_record, disagreement_strings, year_discrepancies).
    year_discrepancies: list of {building_id, adresse, tf_year, ft_year}.
    """
    merged = dict(tf)
    disagreements: list[str] = []
    year_discrepancies: list[dict] = []
    bn_key = tf_row.get("unique_building_name", "?")

    def _plog(col, source_type, drive_id, file_name, src_row, raw, ingested):
        log_provenance(
            target_table="building", target_pk=building_id, target_column=col,
            source_type=source_type,
            source_drive_id=drive_id, source_file_name=file_name,
            source_tab=None, source_row=src_row, source_column=None,
            raw_value=raw, ingested_value=ingested,
        )

    # Log all TF fields. Override entries get ingested_value=None to mark they were superseded.
    tf_drive_id = None  # TF has no Drive ID yet (local upload)
    for col in _ALL_COLS:
        if col in ("raw_fiche_technique", "nb_logements",
                   "systeme_incendie", "boite_a_cle_ext", "boite_a_cle_int"):
            continue  # handled separately
        val = tf.get(col)
        if val is not None:
            if (building_id, col) in _TF_OVERRIDES:
                _plog(col, "table_fondamentale", tf_drive_id, TF_FILE, bn_key, val, None)
            else:
                _plog(col, "TF", tf_drive_id, TF_FILE, bn_key, val, val)

    # Merge FT fields
    if ft_fiche:
        ft_id = ft_fiche["french_drive_id"]
        ft_name = ft_fiche["french_name"]

        # Extract city from FT filename
        city_m = re.search(r",\s*(Qu[ée]bec|L[ée]vis)", ft_fiche["english_name"])
        if city_m and merged.get("ville") is None:
            merged["ville"] = city_m.group(1)
            _plog("ville", "FT", None, LINKS_FILE, ft_fiche["english_name"], city_m.group(1), city_m.group(1))

        for col, (ft_val, entry) in ft_ext.items():
            tf_val = tf.get(col)
            row_ref = str(entry["row"])
            raw = entry["raw_value"]

            if col in _OVERLAP_COLS:
                is_override = (building_id, col) in _TF_OVERRIDES
                if is_override and ft_val is not None:
                    # FT overrides known-wrong TF; TF already logged as overridden above
                    merged[col] = ft_val
                    _plog(col, "fiches_techniques", ft_id, ft_name, row_ref, raw, ft_val)
                elif tf_val is not None:
                    # TF wins — check for disagreement
                    if _disagrees(col, tf_val, ft_val):
                        disagreements.append(
                            f"  building_id={building_id} ({bn_key!r})\n"
                            f"    col={col!r}: TF={tf_val!r}  FT={ft_val!r} (raw={raw!r}) → TF wins"
                        )
                        if col == "annee_construction":
                            # Log the discrepant FT year as a second provenance row (not ingested)
                            _plog(col, "fiches_techniques", ft_id, ft_name, row_ref, raw, None)
                            year_discrepancies.append({
                                "building_id": building_id,
                                "adresse": bn_key,
                                "tf_year": tf_val,
                                "ft_year": str(raw).strip() if raw is not None else str(ft_val),
                            })
                    # Provenance: TF sourced but FT also present
                    _plog(col, "TF", tf_drive_id, TF_FILE, bn_key, tf_val, tf_val)
                else:
                    # TF is None → FT fills
                    merged[col] = ft_val
                    _plog(col, "FT", ft_id, ft_name, row_ref, raw, ft_val)
            else:
                # FT-only column
                merged[col] = ft_val
                _plog(col, "FT", ft_id, ft_name, row_ref, raw, ft_val)

        # raw_fiche_technique blob — full label dump regardless
        merged["raw_fiche_technique"] = {k: v["raw_value"] for k, v in ft_labels.items()}

    return merged, disagreements, year_discrepancies


def _disagrees(col: str, tf_val, ft_val) -> bool:
    """True when the two values represent a genuine disagreement (both non-None)."""
    if tf_val is None or ft_val is None:
        return False
    tv = str(tf_val).strip().lower()
    fv = str(ft_val).strip().lower()
    if tv == fv:
        return False
    # Bool normalisation
    truthy = {"true", "yes", "1", "oui"}
    falsy = {"false", "no", "0", "non"}
    tv_b = True if tv in truthy else (False if tv in falsy else None)
    fv_b = True if fv in truthy else (False if fv in falsy else None)
    if tv_b is not None and fv_b is not None:
        return tv_b != fv_b
    # Numeric: strip ".0" suffix for comparison
    try:
        return float(tv) != float(fv)
    except ValueError:
        return True


# ── MRR crosscheck ────────────────────────────────────────────────────────────

_MRR_BY_FT_EN: dict[str, dict] = {e["ft_english_name"]: e for e in BUILDING_CROSSWALK}


def _mrr_flag(tf_row: dict, ft_fiches: list[dict]) -> str | None:
    """Flag if MRR project name disagrees with TF project name for this building."""
    tf_proj = tf_row.get("unique_project_name", "")

    def _nrm_proj(s: str) -> str:
        s = "".join(
            c for c in unicodedata.normalize("NFD", s.lower())
            if unicodedata.category(c) != "Mn"
        )
        return re.sub(r"[-_\s]+", "", s)

    for fiche in ft_fiches:
        mrr = _MRR_BY_FT_EN.get(fiche["english_name"])
        if not mrr or not mrr.get("mrr_project_name"):
            continue
        mrr_proj = mrr["mrr_project_name"]
        if _nrm_proj(tf_proj) != _nrm_proj(mrr_proj):
            return (
                f"MRR project={mrr_proj!r} ≠ TF project={tf_proj!r} "
                f"[FT: {fiche['english_name']!r}]"
            )
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def run(sample_n: int = 5, verbose: bool = True) -> tuple[list[dict], list[dict]]:
    service = _get_service()

    results: list[dict] = []
    all_disagreements: list[str] = []
    all_year_disc: list[dict] = []
    mrr_flags: list[str] = []
    errors: list[str] = []
    null_counts: dict[str, int] = {col: 0 for col in _ALL_COLS}
    tf_only_count = 0
    ft_matched_count = 0

    for building_id, tf_row in enumerate(TABLE_FONDAMENTALE, 1):
        bn = tf_row.get("unique_building_name", "?")
        tf = _tf_fields(tf_row)

        ft_fiches = _match_tf_to_ft(tf_row)
        ft_fiche = ft_fiches[0] if ft_fiches else None

        ft_labels: dict = {}
        ft_ext: dict = {}

        if ft_fiche:
            try:
                buf = _download_xlsx(service, ft_fiche["french_drive_id"])
                ft_labels = _read_ft_labels(buf)
                ft_ext = _ft_extract(ft_labels)
                ft_matched_count += 1
            except Exception as exc:
                errors.append(f"[{building_id}] {bn!r}: FT download/parse error: {exc}")
                ft_fiche = None
        else:
            tf_only_count += 1

        merged, disagreements, year_disc = _merge_and_log(
            building_id, tf_row, tf, ft_ext, ft_fiche, ft_labels
        )
        merged["building_id"] = building_id

        all_disagreements.extend(disagreements)
        all_year_disc.extend(year_disc)

        flag = _mrr_flag(tf_row, ft_fiches)
        if flag:
            mrr_flags.append(f"  [{building_id}] {bn!r}: {flag}")

        for col in _ALL_COLS:
            if merged.get(col) is None:
                null_counts[col] += 1

        results.append(merged)

    provenance_rows = flush()

    if verbose:
        _print_report(results, provenance_rows, errors, null_counts,
                      all_disagreements, mrr_flags, tf_only_count, ft_matched_count,
                      sample_n, all_year_disc)

    return results, provenance_rows


def _print_report(results, prov_rows, errors, null_counts,
                  disagreements, mrr_flags, tf_only, ft_matched, sample_n,
                  year_disc=None):
    n = len(results)
    print(f"\n{'='*70}")
    print("DRY RUN — ingest_building.py (TF-anchored, TF+FT merge)")
    print(f"{'='*70}")
    print(f"Total buildings (TF rows)   : {n}")
    print(f"  With FT file matched      : {ft_matched}")
    print(f"  TF-only (no FT match)     : {tf_only}")
    print(f"  FT download/parse errors  : {len(errors)}")
    print(f"Provenance rows generated   : {len(prov_rows)}")

    print(f"\n── Field coverage (null count out of {n}) ──")
    # Group by source
    tf_only_cols = [
        "sib_territory", "unique_project_name", "quickbooks_address", "adresse",
        "furnished", "building_structure", "internet", "nb_elevateurs",
        "num_service_elevators", "terrasse_commune", "num_bbqs", "coworking_space",
        "reception_loft", "individual_heat_pumps", "heat_pump_details",
        "chauffage_details", "chauffe_eau",
    ]
    overlap_cols = ["annee_construction", "nb_etages", "ascenseur", "piscine", "sauna", "gym", "chauffage"]
    ft_only_cols = ["ville", "nb_logements", "systeme_incendie", "boite_a_cle_ext", "boite_a_cle_int"]

    def _row(label, col):
        nulls = null_counts.get(col, 0)
        pct = f"{100 * (n - nulls) / n:.0f}%"
        tag = ""
        if col in overlap_cols:
            tag = " [TF+FT overlap]"
        elif col in ft_only_cols:
            tag = " [FT-only]"
        elif col == "raw_fiche_technique":
            tag = " [FT blob]"
        print(f"  {label:<28} {n-nulls:>3}/{n}  ({pct}){tag}")

    print()
    print("  TF-sourced columns:")
    for col in tf_only_cols:
        _row(col, col)
    print()
    print("  Overlap columns (TF wins):")
    for col in overlap_cols:
        _row(col, col)
    print()
    print("  FT-sourced columns:")
    for col in ft_only_cols + ["raw_fiche_technique"]:
        _row(col, col)

    # TF/FT disagreements
    print(f"\n── TF vs FT disagreements ({len(disagreements)} cases) ──")
    if disagreements:
        for d in disagreements:
            print(d)
    else:
        print("  None — TF and FT agree on all overlapping fields where both have data.")

    # Year discrepancies (annee_construction genuine mismatches)
    yd = year_disc or []
    print(f"\n── annee_construction discrepancies ({len(yd)} buildings) ──")
    if yd:
        print(f"  {'building_id':<12} {'TF year':<10} {'FT year':<10} adresse")
        for d in yd:
            print(f"  {d['building_id']:<12} {d['tf_year']:<10} {d['ft_year']:<10} {d['adresse']!r}")
    else:
        print("  None.")

    # Ascenseur overrides
    print(f"\n── Ascenseur TF overrides ({len(_TF_OVERRIDES)} buildings) ──")
    for bid, col in sorted(_TF_OVERRIDES):
        b = next((r for r in results if r.get("building_id") == bid), None)
        adr = b.get("adresse") if b else "?"
        asc = b.get("ascenseur") if b else "?"
        print(f"  building_id={bid} ({adr!r}): ascenseur={asc!r} (FT-sourced, TF was False)")

    # MRR flags
    print(f"\n── MRR project-name disagreements ({len(mrr_flags)}) ──")
    if mrr_flags:
        for f in mrr_flags:
            print(f)
    else:
        print("  None.")

    # Errors
    if errors:
        print(f"\n── FT errors ({len(errors)}) ──")
        for e in errors:
            print(f"  {e}")

    # Sample
    samples = results[:sample_n]
    print(f"\n{'='*70}")
    print(f"SAMPLE — first {len(samples)} buildings")
    print(f"{'='*70}")

    prov_idx: dict[tuple, dict] = {}
    for row in prov_rows:
        prov_idx[(row["target_pk"], row["target_column"])] = row

    for b in samples:
        bid = b["building_id"]
        ft_blob = b.get("raw_fiche_technique")
        print(f"\n── building_id={bid}  {b.get('adresse')!r} ──")
        print(f"   project      : {b.get('unique_project_name')!r}")
        print(f"   territory    : {b.get('sib_territory')!r}")
        print(f"   raw_ft_labels: {len(ft_blob) if ft_blob else 0} labels")
        print()

        for col in _ALL_COLS:
            if col == "raw_fiche_technique":
                continue
            val = b.get(col)
            prov = prov_idx.get((bid, col))
            src = prov["source_type"] if prov else "—"
            flag = "  ← NULL" if val is None else ""
            print(f"   {col:<28} = {str(val):<30} [{src}]{flag}")

    print()


if __name__ == "__main__":
    run()
