"""
ingest_tf_phase1.py — Fill Phase 1 new columns from live Table Fondamentale.

New columns written:
  building: nb_units_total, nb_units_residential, actif_inactif, municipality,
            property_type, dogs_allowed, web_building_name, web_slug
  project:  accounting_project_number

Only writes cells that are currently NULL (idempotent). Does NOT touch any
column that already has a value (protects existing English translations).

Run:
    uv run python -m drive_pipeline.table_fondamentale.ingest_tf_phase1          # dry run
    uv run python -m drive_pipeline.table_fondamentale.ingest_tf_phase1 --write
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as _gapi_build
from googleapiclient.http import MediaIoBaseDownload

from drive_pipeline.ingestion.db import get_conn

_TF_FILE_ID   = "1776VvxgPCtlSzXS238A6sdLjXQ0wG3Qdlf3Fy9dk5SE"
_TF_FILE_NAME = "Table Fondamentale (live)"
_TF_TAB       = "Liste des Projets et Immeubles"
_SCOPES       = ["https://www.googleapis.com/auth/drive"]

# TF column indices (0-based) — verified against live sheet header 2026-10-06
_COL_ACCT_NUM    = 3   # Numero comptable de Projet
_COL_BLDG_NAME   = 6   # Nom Unique d'Immeuble
_COL_NB_TOTAL    = 7   # Nb unités total
_COL_NB_RESID    = 8   # Nb unités résidentielles
_COL_ACTIF       = 13  # Actif / Inactif
_COL_MUNIC       = 16  # Municipalité
_COL_PROP_TYPE   = 17  # Type de propriété
_COL_DOGS        = 52  # Droit aux chiens
_COL_WEB_NAME    = 54  # Nom Unique d'Immeuble pour le Site Web
_COL_WEB_SLUG    = 55  # Slug d'immeuble pour le Site Web


def _creds() -> Credentials:
    c = Credentials.from_authorized_user_file(ROOT / "token.json", _SCOPES)
    if c.expired and c.refresh_token:
        c.refresh(Request())
    return c


def _download_tf() -> list[list]:
    svc = _gapi_build("drive", "v3", credentials=_creds())
    buf = io.BytesIO()
    req = svc.files().export_media(
        fileId=_TF_FILE_ID,
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    wb = openpyxl.load_workbook(io.BytesIO(buf.getvalue()), read_only=True, data_only=True)
    ws = wb[_TF_TAB]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _bool_oui_non(val) -> bool | None:
    s = _str(val)
    if s is None:
        return None
    return s.lower() in ("oui", "yes", "true", "1")


def run(dry_run: bool = True) -> None:
    rows = _download_tf()
    data = [r for r in rows[1:] if any(c is not None for c in r)]
    print(f"TF rows loaded: {len(data)}")

    conn = get_conn()
    cur = conn.cursor()

    # Load building lookup: adresse (lower) → (building_id, project_id)
    cur.execute("SELECT building_id, lower(adresse), project_id FROM building")
    bldg_by_addr: dict[str, tuple[int, int]] = {r[1]: (r[0], r[2]) for r in cur.fetchall()}

    # Load project lookup: project_id → accounting_project_number (to check existing)
    cur.execute("SELECT project_id, accounting_project_number FROM project")
    proj_acct: dict[int, str | None] = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    next_prov = cur.fetchone()[0] + 1

    bldg_updates: list[dict] = []
    proj_updates: list[dict] = []
    unmatched: list[str] = []

    for r in data:
        tf_bldg_name = _str(r[_COL_BLDG_NAME] if _COL_BLDG_NAME < len(r) else None)
        if not tf_bldg_name:
            continue

        match = bldg_by_addr.get(tf_bldg_name.lower())
        if match is None:
            unmatched.append(tf_bldg_name)
            continue

        building_id, project_id = match

        # Building fields (only collect non-None values)
        bldg_cols: dict[str, tuple] = {}  # col_name → (python_val, raw_str, tf_col_idx)

        def _add(col_name: str, val, tf_col: int):
            if val is not None:
                bldg_cols[col_name] = (val, str(r[tf_col]) if tf_col < len(r) else str(val), tf_col)

        _add("nb_units_total",      _int(r[_COL_NB_TOTAL]  if _COL_NB_TOTAL  < len(r) else None), _COL_NB_TOTAL)
        _add("nb_units_residential", _int(r[_COL_NB_RESID] if _COL_NB_RESID  < len(r) else None), _COL_NB_RESID)
        _add("actif_inactif",       _str(r[_COL_ACTIF]     if _COL_ACTIF     < len(r) else None), _COL_ACTIF)
        _add("municipality",        _str(r[_COL_MUNIC]     if _COL_MUNIC     < len(r) else None), _COL_MUNIC)
        _add("property_type",       _str(r[_COL_PROP_TYPE] if _COL_PROP_TYPE < len(r) else None), _COL_PROP_TYPE)
        _add("dogs_allowed",        _bool_oui_non(r[_COL_DOGS] if _COL_DOGS < len(r) else None), _COL_DOGS)
        _add("web_building_name",   _str(r[_COL_WEB_NAME]  if _COL_WEB_NAME  < len(r) else None), _COL_WEB_NAME)
        _add("web_slug",            _str(r[_COL_WEB_SLUG]  if _COL_WEB_SLUG  < len(r) else None), _COL_WEB_SLUG)

        if bldg_cols:
            bldg_updates.append({"building_id": building_id, "cols": bldg_cols})

        # Project: accounting_project_number (stored as float in Excel, e.g. 162.0 → "162")
        _acct_raw = r[_COL_ACCT_NUM] if _COL_ACCT_NUM < len(r) else None
        _acct_int = _int(_acct_raw)
        acct_num = str(_acct_int) if _acct_int is not None else None
        if acct_num and proj_acct.get(project_id) is None:
            proj_updates.append({
                "project_id": project_id,
                "acct_num": acct_num,
                "raw": str(r[_COL_ACCT_NUM]),
            })

    # Deduplicate project updates (multiple buildings share one project)
    seen_projects: set[int] = set()
    proj_updates_dedup = []
    for u in proj_updates:
        if u["project_id"] not in seen_projects:
            seen_projects.add(u["project_id"])
            proj_updates_dedup.append(u)
    proj_updates = proj_updates_dedup

    # Count provenance rows
    prov_count = sum(len(u["cols"]) for u in bldg_updates) + len(proj_updates)

    print(f"Building rows to update: {len(bldg_updates)}")
    print(f"Project rows to update: {len(proj_updates)}")
    print(f"Provenance rows to write: {prov_count}")
    print(f"Unmatched TF building names: {len(unmatched)}")
    for name in unmatched:
        print(f"  UNMATCHED: {name!r}")

    if dry_run:
        print("\nDRY RUN — pass --write to commit")
        # Show a sample
        for u in bldg_updates[:3]:
            print(f"\n  building_id={u['building_id']}:")
            for col, (val, raw, _) in u["cols"].items():
                print(f"    {col} = {val!r}  (raw: {raw!r})")
        conn.close()
        return

    updated_bldgs = 0
    updated_projs = 0

    for u in bldg_updates:
        bid = u["building_id"]
        set_clauses = ", ".join(
            f"{col} = %s" for col in u["cols"]
            # guard: only set if currently NULL
        )
        null_guard = " AND ".join(f"{col} IS NULL" for col in u["cols"])
        vals = [v for v, _, _ in u["cols"].values()]
        cur.execute(
            f"UPDATE building SET {set_clauses} WHERE building_id = %s AND ({null_guard})",
            vals + [bid]
        )
        if cur.rowcount > 0:
            updated_bldgs += 1
            for col, (val, raw, tf_col) in u["cols"].items():
                cur.execute("""
                    INSERT INTO data_provenance
                      (provenance_id, target_table, target_pk, target_column,
                       source_type, source_drive_id, source_file_name, source_tab,
                       source_row, source_column, raw_value, ingested_value)
                    VALUES (%s, 'building', %s, %s, 'google_sheet', %s, %s, %s,
                            NULL, %s, %s, %s)
                """, (next_prov, bid, col, _TF_FILE_ID, _TF_FILE_NAME, _TF_TAB,
                      col, raw, str(val)))
                next_prov += 1

    for u in proj_updates:
        cur.execute("""
            UPDATE project SET accounting_project_number = %s
            WHERE project_id = %s AND accounting_project_number IS NULL
        """, (u["acct_num"], u["project_id"]))
        if cur.rowcount > 0:
            updated_projs += 1
            cur.execute("""
                INSERT INTO data_provenance
                  (provenance_id, target_table, target_pk, target_column,
                   source_type, source_drive_id, source_file_name, source_tab,
                   source_row, source_column, raw_value, ingested_value)
                VALUES (%s, 'project', %s, 'accounting_project_number',
                        'google_sheet', %s, %s, %s, NULL,
                        'accounting_project_number', %s, %s)
            """, (next_prov, u["project_id"], _TF_FILE_ID, _TF_FILE_NAME,
                  _TF_TAB, u["raw"], u["acct_num"]))
            next_prov += 1

    conn.commit()
    print(f"\nCOMMITTED:")
    print(f"  {updated_bldgs} buildings updated")
    print(f"  {updated_projs} projects updated with accounting_project_number")
    conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
