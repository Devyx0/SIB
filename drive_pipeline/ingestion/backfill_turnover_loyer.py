"""
backfill_turnover_loyer.py — Fill unit_turnover.outgoing_fin_bail and outgoing_loyer
from the monthly rent roll archive.

For each unit_turnover row with outgoing_tenant_name_raw set, find the most recent
archive snapshot month where that tenant appears for that unit, and copy fin_bail + loyer.

Source: Google Drive Shared Drive folder 1bBzdogeixb2xE2c5uM703Nu3xjQFJbOR
Usable months: 2025-11, 2026-02 through 2026-08 (see project_status.md §4c).

Run:
    uv run python -m drive_pipeline.ingestion.backfill_turnover_loyer          # dry run
    uv run python -m drive_pipeline.ingestion.backfill_turnover_loyer --write  # write
"""
from __future__ import annotations

import datetime
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
from drive_pipeline.ingestion.ingest_unit_turnover import _norm_key, _resolve_unit, _load_db

_ARCHIVE_FOLDER = "1bBzdogeixb2xE2c5uM703Nu3xjQFJbOR"
_SCOPES = ["https://www.googleapis.com/auth/drive"]

_USABLE_MONTHS: dict[str, datetime.date] = {
    "Rent roll 2025-11": datetime.date(2025, 11, 1),
    "Rent roll 2026-02": datetime.date(2026, 2, 1),
    "Rent roll 2026-03": datetime.date(2026, 3, 1),
    "Rent roll 2026-04": datetime.date(2026, 4, 1),
    "Rent roll 2026-05": datetime.date(2026, 5, 1),
    "Rent roll 2026-06": datetime.date(2026, 6, 1),
    "Rent roll 2026-07": datetime.date(2026, 7, 1),
    "Rent roll 2026-08": datetime.date(2026, 8, 1),
}


def _creds() -> Credentials:
    c = Credentials.from_authorized_user_file(ROOT / "token.json", _SCOPES)
    if c.expired and c.refresh_token:
        c.refresh(Request())
    return c


def _list_archive(svc) -> dict[str, str]:
    files: dict[str, str] = {}
    page_token = None
    while True:
        kwargs: dict = dict(
            q=f"'{_ARCHIVE_FOLDER}' in parents and trashed=false",
            fields="nextPageToken,files(id,name)",
            pageSize=100,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        if page_token:
            kwargs["pageToken"] = page_token
        result = svc.files().list(**kwargs).execute()
        for f in result.get("files", []):
            files[f["name"]] = f["id"]
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return files


def _download_xlsx(svc, file_id: str) -> bytes:
    buf = io.BytesIO()
    req = svc.files().export_media(
        fileId=file_id,
        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def _find_col(headers: list, keywords: list[str]) -> int | None:
    for ci, h in enumerate(headers):
        if h is None:
            continue
        norm = _norm_key(str(h))
        if all(kw in norm for kw in keywords):
            return ci
    return None


def _detect_headers(rows: list[tuple]) -> tuple[list, int]:
    if not rows:
        return [], 2
    h1 = list(rows[0])
    if _find_col(h1, ["unique", "unit"]) is not None:
        return h1, 2
    if len(rows) > 1:
        h2 = list(rows[1])
        merged = [
            f"{h1[i] or ''} {h2[i] if i < len(h2) else ''}".strip()
            for i in range(max(len(h1), len(h2)))
        ]
        if _find_col(merged, ["unique", "unit"]) is not None:
            return merged, 3
    return h1, 2


def _parse_date(val) -> datetime.date | None:
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    s = str(val).strip()
    if not s or s in ("-", "N/A", "#N/A"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _parse_numeric(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return None if v == 0 else v
    s = str(val).strip().replace(",", ".").replace("$", "").replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    try:
        v = float(s)
        return None if v == 0 else v
    except ValueError:
        return None


def _parse_month(data: bytes, file_name: str,
                 bldg_by_addr: dict, unit_by_bldg_apt: dict
                 ) -> dict[int, dict]:
    """
    Parse one month. Returns {unit_id: {nom_norm, fin_bail, loyer}}.
    Only the last entry per unit_id is kept (duplicates unlikely but safe).
    """
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    tab = None
    for name in wb.sheetnames:
        if "rent" in _norm_key(name):
            tab = wb[name]
            break
    if tab is None:
        print(f"  [{file_name}] no 'Rent roll' tab — skipping")
        return {}

    sample_rows = list(tab.iter_rows(min_row=1, max_row=3, values_only=True))
    headers, data_start = _detect_headers(sample_rows)

    c_uid   = _find_col(headers, ["unique", "unit"])
    c_nom   = _find_col(headers, ["nom", "complet"])
    c_fin   = _find_col(headers, ["fin", "bail"])
    c_loyer = _find_col(headers, ["loyer", "base"])

    if c_uid is None:
        print(f"  [{file_name}] cannot detect unit-id column — skipping")
        return {}

    result: dict[int, dict] = {}
    for row in tab.iter_rows(min_row=data_start, values_only=True):
        if c_uid >= len(row):
            continue
        uid_raw = row[c_uid]
        if uid_raw is None or str(uid_raw).strip() in ("", "-"):
            continue
        nom = str(row[c_nom]).strip() if c_nom is not None and c_nom < len(row) and row[c_nom] else None
        if not nom:
            continue
        unit_id = _resolve_unit(str(uid_raw).strip(), bldg_by_addr, unit_by_bldg_apt)
        if unit_id is None:
            continue
        fin  = _parse_date(row[c_fin]   if c_fin   is not None and c_fin   < len(row) else None)
        loyer = _parse_numeric(row[c_loyer] if c_loyer is not None and c_loyer < len(row) else None)
        result[unit_id] = {"nom_norm": _norm_key(nom), "fin_bail": fin, "loyer": loyer}
    return result


def run(dry_run: bool = True) -> None:
    creds = _creds()
    svc = _gapi_build("drive", "v3", credentials=creds)
    archive = _list_archive(svc)
    print(f"Archive: {len(archive)} files")

    conn = get_conn()
    bldg_by_addr, unit_by_bldg_apt, _, _, _ = _load_db(conn)

    # Load all snapshots in chronological order: {source_month: {unit_id: row}}
    snapshots: dict[datetime.date, dict[int, dict]] = {}
    for file_name in sorted(_USABLE_MONTHS, key=lambda n: _USABLE_MONTHS[n]):
        month = _USABLE_MONTHS[file_name]
        fid = archive.get(file_name)
        if not fid:
            print(f"  [{file_name}] not in archive — skipping")
            continue
        snap = _parse_month(_download_xlsx(svc, fid), file_name, bldg_by_addr, unit_by_bldg_apt)
        snapshots[month] = snap
        print(f"  {file_name}: {len(snap)} resolved rows")

    # Load turnover rows that have an outgoing tenant name but no financial data yet
    cur = conn.cursor()
    cur.execute("""
        SELECT turnover_id, unit_id, outgoing_tenant_name_raw,
               move_out_confirmed_date, lease_end_date,
               outgoing_fin_bail, outgoing_loyer
        FROM unit_turnover
        WHERE outgoing_tenant_name_raw IS NOT NULL
    """)
    turnover_rows = cur.fetchall()
    print(f"\nTurnover rows with outgoing tenant name: {len(turnover_rows)}")

    # For each turnover row, find the best matching snapshot:
    # Latest month where (unit_id, norm(outgoing_tenant_name_raw)) appears.
    matched = []
    unmatched = []

    for tid, uid, out_name_raw, move_out_dt, lease_end_dt, existing_fin, existing_loyer in turnover_rows:
        norm_name = _norm_key(out_name_raw)
        # Find the latest snapshot month where this tenant appears for this unit
        best_month = None
        best_data = None
        for month in sorted(snapshots):
            snap = snapshots[month]
            entry = snap.get(uid)
            if entry and entry["nom_norm"] == norm_name:
                best_month = month
                best_data = entry

        if best_data is None:
            unmatched.append((tid, uid, out_name_raw))
            continue

        fin_bail = best_data["fin_bail"]
        loyer    = best_data["loyer"]

        # Skip if both are already set and match — idempotent
        if existing_fin == fin_bail and existing_loyer == loyer:
            continue

        matched.append({
            "turnover_id": tid,
            "unit_id": uid,
            "outgoing_name": out_name_raw,
            "source_month": best_month,
            "fin_bail": fin_bail,
            "loyer": loyer,
            "had_fin": existing_fin,
            "had_loyer": existing_loyer,
        })

    print(f"  Matched (will update): {len(matched)}")
    print(f"  Unmatched (no archive row): {len(unmatched)}")

    print(f"\nSample matches (first 5):")
    for r in matched[:5]:
        print(f"  turnover={r['turnover_id']} unit={r['unit_id']} "
              f"{r['outgoing_name']!r} → fin={r['fin_bail']} loyer={r['loyer']} "
              f"(from {r['source_month']})")

    if dry_run:
        print("\nDRY RUN — pass --write to commit")
        conn.close()
        return

    updated = 0
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    next_prov = cur.fetchone()[0] + 1

    for r in matched:
        cur.execute("""
            UPDATE unit_turnover
               SET outgoing_fin_bail = %s, outgoing_loyer = %s
             WHERE turnover_id = %s
        """, (r["fin_bail"], r["loyer"], r["turnover_id"]))
        if cur.rowcount != 1:
            raise RuntimeError(f"UPDATE affected {cur.rowcount} rows for turnover_id={r['turnover_id']}")
        updated += 1

        for col, val in [("outgoing_fin_bail", r["fin_bail"]),
                         ("outgoing_loyer", r["loyer"])]:
            if val is None:
                continue
            cur.execute("""
                INSERT INTO data_provenance
                  (provenance_id, target_table, target_pk, target_column,
                   source_type, source_drive_id, source_file_name,
                   source_tab, source_row, source_column, raw_value, ingested_value)
                VALUES (%s, 'unit_turnover', %s, %s, 'google_sheet', %s, %s,
                        'Rent roll', NULL, %s, %s, %s)
            """, (next_prov, r["turnover_id"], col,
                  archive.get(f"Rent roll {r['source_month'].strftime('%Y-%m')}",
                              _ARCHIVE_FOLDER),
                  f"Rent roll {r['source_month'].strftime('%Y-%m')}",
                  col, str(val), str(val)))
            next_prov += 1

        if updated % 100 == 0:
            conn.commit()
            print(f"  committed {updated} so far...")

    conn.commit()
    print(f"\nCOMMITTED: {updated} unit_turnover rows updated")
    conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
