"""
ingest_fire_inspection_pdf.py — Extract completed fire inspection data from Drive PDFs.

Writes to:
  - service_visit: UPDATE existing rows with completed_date/result/deficiencies/next_due_date
                   INSERT new rows for additional inspection years (multi-year buildings)
  - building_fire_system: UPDATE panel_brand_model where currently NULL

Source: FIRE PROTECTION folder per-building subfolders (Drive ID _FIRE_FOLDER_ID)

Special cases handled:
  - Cross-building PDFs (Groupe Blais): split on building header, one row each
  - City infraction notices (AVIS D'INFRACTION on page 1): skip
  - Multi-year buildings: one service_visit row per inspection year
  - CORRIGÉ reports: supersede the original for the same year

Run:
    uv run python -m drive_pipeline.ingestion.ingest_fire_inspection_pdf          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_fire_inspection_pdf --write  # write
"""
from __future__ import annotations

import datetime
import io
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import pdfplumber
import pymupdf
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as _gapi_build
from googleapiclient.http import MediaIoBaseDownload
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

_SCOPES          = ["https://www.googleapis.com/auth/drive"]
_FIRE_FOLDER_ID  = "1wEL52LTQBm98xhGEPbq2EaUFhif5PC9t"
_SOURCE_DRIVE_ID = _FIRE_FOLDER_ID
_SOURCE_FILE     = "fire_inspection_pdf"

_SKIP_FOLDERS = {
    "0- Master Fire Protection Table",
    "00- Fire Report Submissions",
    "0-Files Under Review",
    "SI Bélanger - Inspection Report",
}

# Chamonix: 6 buildings share civic 1175 — unit range disambiguates
_CHAMONIX_RANGE_TO_BLDG = {
    (1, 26): 33,
    (27, 63): 34,
    (65, 103): 35,
    (104, 143): 36,
    (144, 169): 37,
    (170, 200): 38,
}

_FR_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

# Vendor names to try matching — longest first to avoid partial matches
_KNOWN_VENDORS = [
    "Groupe Alarme Xpert",
    "Alarme Expert",
    "Groupe Blais",
    "Télé Alarme Plus",
    "Tele Alarme Plus",
    "Québec Pare-Flamme",
    "Quebec Pare-Flamme",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _norm_key(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _v(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


# ── Drive helpers ─────────────────────────────────────────────────────────────

def _get_drive():
    creds = Credentials.from_authorized_user_file(str(ROOT / "token.json"), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return _gapi_build("drive", "v3", credentials=creds)


def _drive_list(drive, **kwargs) -> list[dict]:
    """Execute drive.files().list() with up to 4 retries on 5xx errors."""
    from googleapiclient.errors import HttpError
    for attempt in range(4):
        try:
            return drive.files().list(**kwargs).execute().get("files", [])
        except HttpError as e:
            if e.resp.status < 500 or attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return []


def _list_folders(drive, parent_id: str) -> list[dict]:
    return _drive_list(drive,
        q=(f"'{parent_id}' in parents"
           " and mimeType='application/vnd.google-apps.folder'"
           " and trashed=false"),
        fields="files(id, name)", pageSize=300,
    )


def _list_pdfs(drive, folder_id: str) -> list[dict]:
    return _drive_list(drive,
        q=(f"'{folder_id}' in parents"
           " and mimeType='application/pdf'"
           " and trashed=false"),
        fields="files(id, name)", pageSize=100,
    )


def _list_subfolders(drive, folder_id: str) -> list[dict]:
    return _drive_list(drive,
        q=(f"'{folder_id}' in parents"
           " and mimeType='application/vnd.google-apps.folder'"
           " and trashed=false"),
        fields="files(id, name)", pageSize=100,
    )


def _download(drive, file_id: str) -> bytes:
    buf = io.BytesIO()
    req = drive.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


# ── PDF parsing ───────────────────────────────────────────────────────────────

def _ocr_pdf(pdf_bytes: bytes, lang: str = "fra+eng") -> str:
    """Rasterize all pages with PyMuPDF and OCR with Tesseract (subprocess)."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    mat = pymupdf.Matrix(300 / 72, 300 / 72)
    parts: list[str] = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            pix.save(f.name)
            png_path = f.name
        out = subprocess.run(
            ["tesseract", png_path, "stdout", "-l", lang, "--psm", "6"],
            capture_output=True, text=True,
        )
        Path(png_path).unlink(missing_ok=True)
        parts.append(out.stdout)
    doc.close()
    return "\n".join(parts)


def _extract_text(pdf_bytes: bytes) -> tuple[str, bool]:
    """Return (text, is_ocr). is_ocr=True means pdfplumber found no text and OCR was used."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]
    if any(t.strip() for t in pages_text):
        return "\n".join(pages_text), False
    return _ocr_pdf(pdf_bytes), True


def _is_infraction_notice(text: str) -> bool:
    return bool(re.search(r"AVIS\s+D.INFRACTION", text[:2000], re.IGNORECASE))


def _parse_inspection_date(text: str) -> datetime.date | None:
    # Prefer "DATE : DD/MM/YYYY" or "DATE : 15 mars 2025" — anchored form guards against
    # template dates that OCR finds before the actual inspection date field.
    m = re.search(r"DATE\s*:\s*(\d{1,2})[/\-](\d{2})[/\-](\d{4})", text, re.IGNORECASE)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(
        r"DATE\s*:\s*(?:le\s+|du\s+)?(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin"
        r"|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre),?\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        month = _FR_MONTHS.get(m.group(2).lower())
        if month:
            return datetime.date(int(m.group(3)), month, int(m.group(1)))

    # Unanchored fallback — "15 mars 2025", "le 15 mars 2025", "en date du 15 mars 2025"
    m = re.search(
        r"(?:le\s+|du\s+)?(\d{1,2})\s+(janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t"
        r"|septembre|octobre|novembre|d[eé]cembre),?\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        month = _FR_MONTHS.get(m.group(2).lower())
        if month:
            return datetime.date(int(m.group(3)), month, int(m.group(1)))
    # DD/MM/YYYY
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_result(text: str) -> str:
    """'conditional' if deficiencies noted, else 'pass'."""
    lower = text.lower()
    if re.search(r"pr[eé]sente\s+des\s+lacunes", lower):
        return "conditional"
    if re.search(r"lacune", lower):
        return "conditional"
    return "pass"


def _parse_panel(text: str) -> str | None:
    # Brand + model code patterns — "MODÈLE" / "MODEL" may appear between brand and code
    _BRAND_MODELS = [
        (r"Mircom",   r"(FA-\d+[A-Z0-9.-]*)"),
        (r"Mircom",   r"(FX-\d+[A-Z0-9.-]*)"),
        (r"Mircom",   r"(BPS-\d+[A-Z0-9.-]*)"),
        (r"Potter",   r"(PFC\d+[A-Z0-9.-]*)"),
        (r"Edwards?", r"(\d{4}[A-Z]*)"),
        (r"Simplex",  r"(\d{4}[A-Z0-9.-]*)"),
        (r"DSC",      r"(PC-\d+[A-Z0-9.-]*)"),
        (r"Hochiki",  r"([A-Z]{2,4}\d+[A-Z0-9.-]*)"),
        (r"Secutron", r"(MR-\d+[A-Z0-9.-]*)"),
    ]
    for brand_pat, model_pat in _BRAND_MODELS:
        m = re.search(
            rf"({brand_pat})\s*(?:MOD[EÈ]LE?\s*[:/]?\s*)?{model_pat}",
            text, re.IGNORECASE,
        )
        if m:
            return f"{m.group(1)} {m.group(2)}".strip()
    # Fallback: value following "MODÈLE :" when brand appears elsewhere
    m = re.search(r"MOD[EÈ]LE\s*[:/]?\s*([A-Z]{2,}-\d+[A-Z0-9.-]*)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _has_model_code(val: str | None) -> bool:
    """True when val contains a specific model code, not just a brand name."""
    if not val:
        return False
    return bool(re.search(r"(?:FX|FA|BPS|PFC|PC|MR)-\d+|\b\d{4}[A-Z]?\b", val, re.IGNORECASE))


_KNOWN_BRANDS = {
    "mircom", "potter", "edwards", "simplex", "dsc", "hochiki",
    "secutron", "vigilant", "chubb", "notifier", "siemens", "firelite",
}


def _panel_has_brand(val: str | None) -> bool:
    """True when val contains a recognizable manufacturer name."""
    if not val:
        return False
    n = _norm_key(val)
    return any(b in n for b in _KNOWN_BRANDS)


def _parse_deficiencies(text: str) -> str | None:
    codes: list[str] = []
    codes += re.findall(r"\b(L\d{1,4}|REC\d{1,3})\b", text)           # L110, REC26
    codes += [f"L{m}" for m in re.findall(r"\bL\.(\d{1,4})\b", text)] # L.110 → L110
    for m in re.finditer(r"Lacune[s]?\s+(\d{1,4})", text, re.IGNORECASE):
        codes.append(f"L{m.group(1)}")
    if not codes:
        return None
    seen: set[str] = set()
    unique = [c for c in codes if not (c in seen or seen.add(c))]
    return "; ".join(unique[:20])


def _parse_vendor_name(text: str) -> str | None:
    for vendor in _KNOWN_VENDORS:
        if vendor.lower() in text.lower():
            return vendor
    return None


def _parse_rbq(text: str) -> str | None:
    m = re.search(r"\b(\d{4}-\d{4}-\d{2})\b", text)
    return m.group(1) if m else None


def _parse_address_from_text(text: str) -> tuple[str | None, str | None]:
    """Try to extract civic + street from the first 2000 chars of text."""
    snippet = text[:2000]
    # Street may start with ordinal digits (48e, 4e) or letters
    m = re.search(
        r"(\d{3,5}(?:[-–]\d{3,5})?)[,\s]+((?:\d+[eèéème.]*\s+)?[A-ZÀ-Ÿa-zà-ÿ][A-ZÀ-Ÿa-zà-ÿ0-9 .'-]+)",
        snippet,
    )
    if m:
        return m.group(1).split("-")[0].split("–")[0], m.group(2).strip().rstrip(",")
    return None, None


# ── Multi-building PDF splitting (Groupe Blais) ───────────────────────────────

_SIB_HDR_RE = re.compile(r"SOC\.IMM\.B[EÉ]LANGER\s*\(([^)]+)\)", re.IGNORECASE)


def _split_by_building_headers(text: str) -> list[tuple[str, str]]:
    """
    Split a Groupe Blais multi-building PDF on SOC.IMM.BÉLANGER(address) headers.
    Returns [(address_hint, section_text), ...].
    """
    matches = list(_SIB_HDR_RE.finditer(text))
    if len(matches) <= 1:
        return [("", text)]
    # Preamble (before first header) often contains the date and vendor info —
    # include it in every section so date/vendor parsing works per section.
    preamble = text[:matches[0].start()]
    sections = []
    for i, m in enumerate(matches):
        addr = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((addr, preamble + text[start:end]))
    return sections


# ── Building address → building_id matching ───────────────────────────────────

_CIVIC_RE = re.compile(r"^(\d+(?:[-–]\d+)*)\s+(.+)")


def _folder_name_to_civic_street(folder_name: str) -> tuple[str | None, str | None]:
    """'FRANCE-PRIME 3150' → ('3150', 'France-Prime'), '7-11 DE LA TERRASSE' → ('7', 'Terrasse...')"""
    name = folder_name.strip()
    # Pattern 0: civic in parens — "Sully Ave, Québec (7885) (24 to 46)"
    m = re.search(r"\((\d{2,5})\)", name)
    if m:
        civic = m.group(1)
        street = re.sub(r"\s*\(.*", "", name).rstrip(", ")
        if street and not re.search(r"\d", street):
            return civic, street
    # Pattern 1: ends with civic — "FRANCE-PRIME 3150", "Carmichael 85", "Confluent 4032-4034-4040"
    m = re.match(r"(.+?)\s+(\d+(?:[-–]\d+)*)$", name)
    if m:
        civic = m.group(2).split("-")[0].split("–")[0]
        street = m.group(1).strip()
        # Short civics (1-2 digits) are only safe when the street has no embedded numbers;
        # longer civics (3+ digits) are unambiguous even in multi-building folder names.
        if len(civic) >= 3 or not re.search(r"\d", street):
            return civic, street
    # Pattern 2: starts with civic range — "7-11 DE LA TERRASSE-ORLÉANS"
    m = re.match(r"(\d+)[-–\s]+(\d+)?\s+(.+)", name)
    if m:
        return m.group(1), m.group(3).strip()
    m = _CIVIC_RE.match(name)
    if m:
        return m.group(1).split("-")[0].split("–")[0], m.group(2).strip()
    return None, None


def _match_unit_range_cluster(folder_name: str) -> int | None:
    """Match Chamonix folders (same civic, unit range disambiguates) to building_id."""
    if "chamonix" not in folder_name.lower():
        return None
    m = re.search(r"\((\d+)\s+(?:to|[àa])\s+(\d+)\)", folder_name, re.IGNORECASE)
    if not m:
        return None
    return _CHAMONIX_RANGE_TO_BLDG.get((int(m.group(1)), int(m.group(2))))


def _clean_street(s: str) -> str:
    """Normalize apostrophes/quotes to space so _match_building normalization works."""
    return re.sub(r"['‘’ʼ]", " ", s)


def _resolve_building(folder_name: str, addr_hint: str, bldg_by_addr: dict) -> int | None:
    """Try multiple strategies to find building_id."""
    # Direct folder name match (civic prefixed in DB)
    m = _CIVIC_RE.match(folder_name.strip())
    if m:
        civic = m.group(1).split("-")[0].split("–")[0]
        street = m.group(2).strip()
        row = _match_building(_clean_street(street), civic, None)
        if row:
            bid = bldg_by_addr.get(row.get("unique_building_name"))
            if bid:
                return bid

    # Street+civic from folder name reversed
    civic, street = _folder_name_to_civic_street(folder_name)
    if civic and street:
        row = _match_building(_clean_street(street), civic, None)
        if row:
            bid = bldg_by_addr.get(row.get("unique_building_name"))
            if bid:
                return bid

    # addr_hint from cross-building PDF header
    if addr_hint:
        m2 = _CIVIC_RE.match(addr_hint.strip())
        if m2:
            civic2 = m2.group(1).split("-")[0].split("–")[0]
            street2 = m2.group(2).strip()
            row = _match_building(_clean_street(street2), civic2, None)
            if row:
                bid = bldg_by_addr.get(row.get("unique_building_name"))
                if bid:
                    return bid
        # Reversed addr_hint (street first)
        m3 = re.match(r"(.+?)\s+(\d+(?:[-–]\d+)*)$", addr_hint.strip())
        if m3:
            civic3 = m3.group(2).split("-")[0].split("–")[0]
            street3 = m3.group(1).strip()
            if not re.search(r"\d", street3):
                row = _match_building(_clean_street(street3), civic3, None)
                if row:
                    bid = bldg_by_addr.get(row.get("unique_building_name"))
                    if bid:
                        return bid

    # Direct DB scan — catches buildings not in Table Fondamentale
    # Try both folder_name and addr_hint civic+street against bldg_by_addr
    for src in [folder_name, addr_hint]:
        if not src:
            continue
        cv, st = _folder_name_to_civic_street(src)
        if not cv or not st:
            continue
        cv_n = _norm_key(cv)
        st_words = [w for w in _norm_key(st).split() if len(w) >= 4]
        if not st_words:
            continue
        for addr, bid in bldg_by_addr.items():
            a_n = _norm_key(addr)
            if cv_n in a_n and any(sw in a_n for sw in st_words):
                return bid

    return None


# ── Year extraction from filename ─────────────────────────────────────────────

def _year_from_filename(name: str) -> int | None:
    m = re.search(r"\b(20[12]\d)\b", name)
    return int(m.group(1)) if m else None


def _is_corrige(name: str) -> bool:
    return bool(re.search(r"corrig[eé]", name, re.IGNORECASE))


# ── Main ingestion dataclass ──────────────────────────────────────────────────

@dataclass
class InspectionRecord:
    building_id:    int
    folder_name:    str
    file_name:      str
    file_id:        str
    year:           int | None
    is_corrige:     bool
    completed_date: datetime.date | None
    result:         str | None
    deficiencies:   str | None
    next_due_date:  datetime.date | None
    panel:          str | None
    vendor_name:    str | None
    vendor_rbq:     str | None
    vendor_id:      int | None = None
    addr_hint:      str = ""
    is_ocr:         bool = False


# ── DB state ──────────────────────────────────────────────────────────────────

def _load_db(conn):
    cur = conn.cursor()
    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(
        "SELECT visit_id, building_id, completed_date, deficiencies, next_due_date, result"
        "  FROM service_visit WHERE visit_type = 'fire_inspection'"
    )
    # building_id → list of (visit_id, completed_date, deficiencies, next_due_date, result)
    existing_visits: dict[int, list] = {}
    for row in cur.fetchall():
        vid, bid, cd, defc, ndd, res = row
        existing_visits.setdefault(bid, []).append({
            "visit_id": vid, "completed_date": cd,
            "deficiencies": defc, "next_due_date": ndd, "result": res,
        })

    cur.execute(
        "SELECT fire_system_id, building_id, panel_brand_model"
        "  FROM building_fire_system"
    )
    existing_bfs: dict[int, dict] = {}
    for row in cur.fetchall():
        fsid, bid, panel = row
        existing_bfs[bid] = {"fire_system_id": fsid, "panel_brand_model": panel}

    cur.execute("SELECT vendor_id, nom FROM vendor_contact")
    vendor_by_norm = {_norm_key(nom): vid for vid, nom in cur.fetchall()}

    cur.execute("SELECT COALESCE(MAX(visit_id), 0) FROM service_visit")
    max_visit_id = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    max_prov_id = cur.fetchone()[0]

    return bldg_by_addr, existing_visits, existing_bfs, vendor_by_norm, max_visit_id, max_prov_id


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool = True) -> None:
    conn = get_conn()
    (bldg_by_addr, existing_visits, existing_bfs,
     vendor_by_norm, max_visit_id, max_prov_id) = _load_db(conn)
    conn.close()

    drive = _get_drive()

    folders = _list_folders(drive, _FIRE_FOLDER_ID)
    building_folders = [f for f in folders if f["name"] not in _SKIP_FOLDERS]

    print(f"\n=== ingest_fire_inspection_pdf {'DRY RUN' if dry_run else 'WRITE'} ===")
    print(f"Building folders found: {len(building_folders)}")

    records: list[InspectionRecord] = []
    skipped_notices = 0
    unmatched_folders: list[str] = []
    download_errors: list[str] = []

    for folder in building_folders:
        folder_id   = folder["id"]
        folder_name = folder["name"]

        # Some building folders have sub-year folders (e.g. France-Prime 3150: 2021, 2025, 2026)
        sub_folders = _list_subfolders(drive, folder_id)
        pdf_sources: list[tuple[str, list[dict]]] = []  # (subfolder_name, pdfs)
        if sub_folders:
            for sf in sub_folders:
                pdfs = _list_pdfs(drive, sf["id"])
                if pdfs:
                    pdf_sources.append((sf["name"], pdfs))
        direct_pdfs = _list_pdfs(drive, folder_id)
        if direct_pdfs:
            pdf_sources.append(("", direct_pdfs))

        if not pdf_sources:
            unmatched_folders.append(f"{folder_name} (no PDFs)")
            continue

        # Collect all PDF candidates and de-duplicate by year (prefer CORRIGÉ)
        year_pdfs: dict[int | None, dict] = {}
        no_year_pdfs: list[dict] = []
        for subfolder_label, pdfs in pdf_sources:
            for pdf in pdfs:
                name = pdf["name"]
                year = _year_from_filename(name) or _year_from_filename(subfolder_label)
                corrige = _is_corrige(name)
                candidate = {**pdf, "year": year, "is_corrige": corrige,
                             "subfolder": subfolder_label}
                if year is not None:
                    existing = year_pdfs.get(year)
                    if existing is None or (not existing["is_corrige"] and corrige):
                        year_pdfs[year] = candidate
                else:
                    no_year_pdfs.append(candidate)

        all_candidates = list(year_pdfs.values()) + no_year_pdfs

        for pdf_info in all_candidates:
            file_id   = pdf_info["id"]
            file_name = pdf_info["name"]
            year      = pdf_info.get("year")
            is_corrige = pdf_info.get("is_corrige", False)

            try:
                pdf_bytes = _download(drive, file_id)
                text, is_ocr_pdf = _extract_text(pdf_bytes)
            except Exception as e:
                download_errors.append(f"{folder_name}/{file_name}: {e}")
                continue

            if _is_infraction_notice(text):
                skipped_notices += 1
                continue

            # Split multi-building PDFs (Groupe Blais)
            sections = _split_by_building_headers(text)

            for addr_hint, section_text in sections:
                completed_date = _parse_inspection_date(section_text)
                # Guard: reject dates outside plausible range (catches OCR artifacts like 2000-11-07)
                if completed_date and not (2010 <= completed_date.year <= 2028):
                    completed_date = None
                result         = _parse_result(section_text)
                deficiencies   = _parse_deficiencies(section_text)
                panel          = _parse_panel(section_text)
                vendor_name    = _parse_vendor_name(section_text)
                vendor_rbq     = _parse_rbq(section_text)

                # Use section year if file year unknown
                if completed_date and year is None:
                    year = completed_date.year
                next_due = (
                    datetime.date(completed_date.year + 1, completed_date.month,
                                  completed_date.day)
                    if completed_date else None
                )

                # Resolve vendor_id
                vendor_id = None
                if vendor_name:
                    vendor_id = vendor_by_norm.get(_norm_key(vendor_name))

                # Resolve building_id: try addr_hint/folder → unit-range cluster → PDF text
                building_id = _resolve_building(addr_hint or folder_name, addr_hint, bldg_by_addr)
                if building_id is None:
                    building_id = _match_unit_range_cluster(folder_name)
                if building_id is None:
                    pdf_civic, pdf_street = _parse_address_from_text(section_text)
                    if pdf_civic and pdf_street:
                        row = _match_building(pdf_street, pdf_civic, None)
                        if row:
                            building_id = bldg_by_addr.get(row.get("unique_building_name"))
                if building_id is None:
                    if addr_hint:
                        unmatched_folders.append(f"{folder_name}/{file_name} section={addr_hint!r}")
                    else:
                        unmatched_folders.append(f"{folder_name}/{file_name}")
                    continue

                records.append(InspectionRecord(
                    building_id    = building_id,
                    folder_name    = folder_name,
                    file_name      = file_name,
                    file_id        = file_id,
                    year           = year,
                    is_corrige     = is_corrige,
                    completed_date = completed_date,
                    result         = result,
                    deficiencies   = deficiencies,
                    next_due_date  = next_due,
                    panel          = panel,
                    vendor_name    = vendor_name,
                    vendor_rbq     = vendor_rbq,
                    vendor_id      = vendor_id,
                    addr_hint      = addr_hint,
                    is_ocr         = is_ocr_pdf,
                ))

    # ── Compute changes ───────────────────────────────────────────────────────

    # Group records by building_id, pick most-recent for the UPDATE target
    by_building: dict[int, list[InspectionRecord]] = {}
    for rec in records:
        by_building.setdefault(rec.building_id, []).append(rec)

    visit_updates: list[dict] = []    # UPDATE existing service_visit
    visit_inserts: list[dict] = []    # INSERT new service_visit rows
    bfs_updates:   list[dict] = []    # UPDATE building_fire_system.panel_brand_model

    visit_id_seq = max_visit_id

    for bid, recs in sorted(by_building.items()):
        recs_sorted = sorted(
            recs,
            key=lambda r: (r.completed_date or datetime.date.min),
        )
        existing = existing_visits.get(bid, [])
        # Find the existing visit row with NULL completed_date (the scheduled one)
        target_visit = next((v for v in existing if v["completed_date"] is None), None)
        if target_visit is None and existing:
            target_visit = existing[0]  # fallback: use first row

        for i, rec in enumerate(recs_sorted):
            if i == len(recs_sorted) - 1 and target_visit:
                # Most recent year → UPDATE the existing row
                visit_updates.append({
                    "visit_id":        target_visit["visit_id"],
                    "building_id":     bid,
                    "completed_date":  rec.completed_date,
                    "result":          rec.result,
                    "deficiencies":    rec.deficiencies,
                    "next_due_date":   rec.next_due_date,
                    "vendor_id":       rec.vendor_id,
                    "source_file":     rec.file_name,
                    "rec":             rec,
                })
            else:
                # Additional years → INSERT new rows
                visit_id_seq += 1
                visit_inserts.append({
                    "visit_id":       visit_id_seq,
                    "building_id":    bid,
                    "vendor_id":      rec.vendor_id,
                    "completed_date": rec.completed_date,
                    "result":         rec.result,
                    "deficiencies":   rec.deficiencies,
                    "next_due_date":  rec.next_due_date,
                    "source_file":    rec.file_name,
                    "rec":            rec,
                })

        # Panel update — use most recent non-null panel value
        best_panel = next(
            (r.panel for r in reversed(recs_sorted) if r.panel), None
        )
        bfs = existing_bfs.get(bid)
        if best_panel and bfs:
            old_panel = bfs["panel_brand_model"]
            # Guard 1: never overwrite a specific model code with a less-specific extraction
            if _has_model_code(old_panel) and not _has_model_code(best_panel):
                continue
            # Guard 2: never overwrite a value that has a brand name with one that doesn't
            if _panel_has_brand(old_panel) and not _panel_has_brand(best_panel):
                continue
            # Flag brand changes: both must have recognizable brand names that differ
            old_brand_n = _norm_key((old_panel or "").split()[0]) if old_panel else ""
            new_brand_n = _norm_key(best_panel.split()[0]) if best_panel else ""
            brand_change = (
                _panel_has_brand(old_panel) and _panel_has_brand(best_panel)
                and old_brand_n != new_brand_n
            )
            bfs_updates.append({
                "fire_system_id":  bfs["fire_system_id"],
                "building_id":     bid,
                "old_panel":       old_panel,
                "new_panel":       best_panel,
                "recs":            recs_sorted,
                "brand_change":    brand_change,
            })

    # ── Dry run report ────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"INSPECTION RECORDS PARSED: {len(records)}")
    print(f"Buildings covered:          {len(by_building)}")
    print(f"Notices skipped:            {skipped_notices}")
    print(f"Download errors:            {len(download_errors)}")
    print(f"Unmatched folders/sections: {len(unmatched_folders)}")
    print()
    print(f"service_visit UPDATEs:      {len(visit_updates)}")
    print(f"service_visit INSERTs:      {len(visit_inserts)}")
    print(f"building_fire_system UPDTs: {len(bfs_updates)}")
    print()

    print("── service_visit UPDATEs (sample, first 20) ─────────────────────")
    for u in visit_updates[:20]:
        rec = u["rec"]
        print(f"  visit_id={u['visit_id']} bldg={u['building_id']} ({rec.folder_name})")
        print(f"    pdf={rec.file_name}")
        print(f"    completed={u['completed_date']} result={u['result']}")
        print(f"    deficiencies={u['deficiencies']!r}")
        print(f"    next_due={u['next_due_date']} vendor_id={u['vendor_id']}")
    if len(visit_updates) > 20:
        print(f"  ... +{len(visit_updates)-20} more")

    print()
    print("── service_visit INSERTs (additional years) ──────────────────────")
    for ins in visit_inserts:
        rec = ins["rec"]
        print(f"  NEW visit_id={ins['visit_id']} bldg={ins['building_id']} year={rec.year}")
        print(f"    completed={ins['completed_date']} result={ins['result']}")
        print(f"    deficiencies={ins['deficiencies']!r}")

    print()
    print("── building_fire_system UPDATEs (panel_brand_model) ─────────────")
    for b in bfs_updates[:40]:
        changed = b["old_panel"] != b["new_panel"]
        if b.get("brand_change"):
            status = "BRAND_CHANGE ⚠"
        elif changed:
            status = "CHANGE"
        else:
            status = "same"
        print(f"  fire_system_id={b['fire_system_id']} bldg={b['building_id']}: "
              f"{b['old_panel']!r} → {b['new_panel']!r}  [{status}]")
    actual_updates = sum(1 for b in bfs_updates if b["old_panel"] != b["new_panel"])
    brand_changes = sum(1 for b in bfs_updates if b.get("brand_change"))
    if len(bfs_updates) > 40:
        print(f"  ... +{len(bfs_updates)-40} more")
    print(f"  Net panel changes: {actual_updates} / {len(bfs_updates)}  (brand changes: {brand_changes})")
    if brand_changes:
        print("  NOTE: review BRAND_CHANGE entries above before --write")

    if unmatched_folders:
        print()
        print("── Unmatched (no building_id) ────────────────────────────────────")
        for u in unmatched_folders:
            print(f"  - {u}")

    if download_errors:
        print()
        print("── Download errors ───────────────────────────────────────────────")
        for e in download_errors:
            print(f"  - {e}")

    if dry_run:
        print(f"\nDRY RUN — pass --write to commit.")
        return

    # ── Write ─────────────────────────────────────────────────────────────────
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]
        prov_seq = prov_offset

        # service_visit UPDATEs
        for u in visit_updates:
            rec = u["rec"]
            cur.execute(
                """UPDATE service_visit
                   SET completed_date=%s, result=%s, deficiencies=%s,
                       next_due_date=%s, vendor_id=COALESCE(vendor_id, %s)
                   WHERE visit_id=%s""",
                (u["completed_date"], u["result"], u["deficiencies"],
                 u["next_due_date"], u["vendor_id"], u["visit_id"]),
            )
            src_type = "pdf_ocr" if rec.is_ocr else "pdf"
            for col, raw, ing in [
                ("completed_date", str(rec.completed_date), str(u["completed_date"])),
                ("result",         rec.result,              u["result"]),
                ("deficiencies",   rec.deficiencies,        u["deficiencies"]),
                ("next_due_date",  str(rec.next_due_date),  str(u["next_due_date"])),
            ]:
                if raw is None and ing is None:
                    continue
                prov_seq += 1
                cur.execute(
                    """INSERT INTO data_provenance
                       (provenance_id, target_table, target_pk, target_column,
                        source_type, source_drive_id, source_file_name,
                        source_tab, source_row, source_column, raw_value, ingested_value)
                       VALUES (%s,'service_visit',%s,%s,%s,%s,%s,NULL,NULL,NULL,%s,%s)""",
                    (prov_seq, str(u["visit_id"]), col,
                     src_type, rec.file_id, rec.file_name, raw, ing),
                )

        # service_visit INSERTs
        if visit_inserts:
            execute_values(
                cur,
                """INSERT INTO service_visit
                   (visit_id, building_id, vendor_id, equipment_id, visit_type,
                    due_date, completed_date, result, deficiencies, next_due_date)
                   VALUES %s""",
                [(ins["visit_id"], ins["building_id"], ins["vendor_id"], None,
                  "fire_inspection", None,
                  ins["completed_date"], ins["result"], ins["deficiencies"],
                  ins["next_due_date"])
                 for ins in visit_inserts],
                page_size=200,
            )
            for ins in visit_inserts:
                rec = ins["rec"]
                src_type = "pdf_ocr" if rec.is_ocr else "pdf"
                for col, raw, ing in [
                    ("building_id",    str(rec.building_id),    str(ins["building_id"])),
                    ("completed_date", str(rec.completed_date), str(ins["completed_date"])),
                    ("result",         rec.result,              ins["result"]),
                ]:
                    prov_seq += 1
                    cur.execute(
                        """INSERT INTO data_provenance
                           (provenance_id, target_table, target_pk, target_column,
                            source_type, source_drive_id, source_file_name,
                            source_tab, source_row, source_column, raw_value, ingested_value)
                           VALUES (%s,'service_visit',%s,%s,%s,%s,%s,NULL,NULL,NULL,%s,%s)""",
                        (prov_seq, str(ins["visit_id"]), col,
                         src_type, rec.file_id, rec.file_name, raw, ing),
                    )

        # building_fire_system UPDATEs — building 1 panel held pending physical verification
        for b in bfs_updates:
            if b["old_panel"] == b["new_panel"]:
                continue
            if b["building_id"] == 1:
                continue  # FA-100 vs FA-1000 unresolved; held for client confirmation
            cur.execute(
                "UPDATE building_fire_system SET panel_brand_model=%s WHERE fire_system_id=%s",
                (b["new_panel"], b["fire_system_id"]),
            )
            prov_seq += 1
            rec0 = b["recs"][-1]
            src_type = "pdf_ocr" if rec0.is_ocr else "pdf"
            cur.execute(
                """INSERT INTO data_provenance
                   (provenance_id, target_table, target_pk, target_column,
                    source_type, source_drive_id, source_file_name,
                    source_tab, source_row, source_column, raw_value, ingested_value)
                   VALUES (%s,'building_fire_system',%s,'panel_brand_model',%s,%s,%s,NULL,NULL,NULL,%s,%s)""",
                (prov_seq, str(b["fire_system_id"]),
                 src_type, rec0.file_id, rec0.file_name, b["new_panel"], b["new_panel"]),
            )

        conn.commit()

        cur.execute("SELECT COUNT(*) FROM service_visit WHERE completed_date IS NOT NULL")
        sv_done = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM service_visit")
        sv_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM building_fire_system WHERE panel_brand_model IS NOT NULL")
        bfs_panel = cur.fetchone()[0]

        print(f"\nCommitted:")
        print(f"  service_visit UPDATEs: {len(visit_updates)}")
        print(f"  service_visit INSERTs: {len(visit_inserts)}")
        print(f"  building_fire_system panel updates: {actual_updates}")
        print(f"  provenance rows: {prov_seq - prov_offset}")
        print(f"\nDB totals:")
        print(f"  service_visit: {sv_total} total, {sv_done} with completed_date")
        print(f"  building_fire_system: {bfs_panel} with panel_brand_model")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
