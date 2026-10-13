"""
ingest_emergency_access_code.py — Emergency access codes from emergency contacts file.

Source: '0 - EMERGENCY CONTACTS AND PROCEDURES.xlsx' (French original, Fiches Techniques root)
Drive ID: 1JRG7fLlSAWfLz6XBbwK_Emiqqj-sdtzA
Tab: 'Adresse'

Rows ingested:
  - Global key box codes (R4 col B): 6 codes (Haute-Ville new, maintenance new/old,
    construction, transition, keyless intercom)
  - WiFi code (R29 col B): 1 code
  - Zone emergency key boxes (R41–R46): 6 zones × 1 box code = 6 rows,
    plus 1 keyless-entry code for Lebourgneuf/Montchatel = 7 rows

SECURITY: code_value is written normally to the DB column.
          data_provenance raw_value/ingested_value = '[REDACTED-SENSITIVE]'.
          Console/dry-run output shows [populated] or [null], never the actual code.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_emergency_access_code          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_emergency_access_code --write  # write
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as _gapi_build
from googleapiclient.http import MediaIoBaseDownload
import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn

_SCOPES   = ["https://www.googleapis.com/auth/drive"]
_DRIVE_ID = "1JRG7fLlSAWfLz6XBbwK_Emiqqj-sdtzA"
_TAB      = "Adresse"
_SOURCE   = "0 - EMERGENCY CONTACTS AND PROCEDURES.xlsx"

# Zone row indices in sheet → (zone_name, building_id of physical key box)
_ZONE_ROWS = {
    41: ("Haute-Ville",             107),  # box at 315-317 St-Jean
    42: ("Limoilou/Vanier",         107),  # box at 315-317 St-Jean
    43: ("Lévis",                   107),  # box at 315-317 St-Jean
    44: ("Ste-Foy",                  91),  # box at 1017 Duchesneau
    45: ("Lebourgneuf/Montchatel",   77),  # box at 5875 Costebelle
    46: ("Charlesbourg/Beauport",   107),  # box at 315-317 St-Jean
}


def _fetch_ws():
    creds = Credentials.from_authorized_user_file(str(ROOT / "token.json"), _SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    drive = _gapi_build("drive", "v3", credentials=creds)
    buf = io.BytesIO()
    req = drive.files().get_media(fileId=_DRIVE_ID)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return openpyxl.load_workbook(buf, data_only=True)[_TAB]


def _parse_rows(ws) -> list[dict]:
    """Extract all code rows from the sheet. Returns list of row dicts."""
    rows: list[dict] = []

    # ── R4: "Code boite a clé" — multiple codes embedded in col B ─────────────
    r4_raw = ws.cell(4, 2).value or ""
    # Labels we care about and their code_type
    _R4_LABELS = [
        (r"Nouveau\s+Haute.ville",           "key_box_haute_ville_new"),
        (r"Nouveau\s+maintenance",            "key_box_maintenance_new"),
        (r"Ancien\s+maintenance",             "key_box_maintenance_old"),
        (r"Code\s+construction",              "key_box_construction"),
        (r"Code\s+immeuble\s+transition",     "key_box_transition"),
        (r"Code\s+intercom\s+Key\s+less",     "keyless_intercom"),
    ]
    for pattern, code_type in _R4_LABELS:
        # Match "Label : CODE" or "Label: CODE"
        m = re.search(pattern + r"\s*:?\s*code\s+(\S+)", r4_raw, re.IGNORECASE)
        if not m:
            m = re.search(pattern + r"\s*:?\s*(\d+)", r4_raw, re.IGNORECASE)
        if m:
            rows.append({
                "building_id":  None,
                "zone_name":    None,
                "code_type":    code_type,
                "code_value":   m.group(1).strip(),
                "source_row":   4,
            })

    # ── R29: Internet / WiFi code ─────────────────────────────────────────────
    r29_raw = ws.cell(29, 2).value or ""
    m = re.search(r"Code\s*:\s*(\S+)", r29_raw, re.IGNORECASE)
    if m:
        rows.append({
            "building_id":  None,
            "zone_name":    None,
            "code_type":    "wifi",
            "code_value":   m.group(1).strip(),
            "source_row":   29,
        })

    # ── R41–R46: Zone emergency key boxes ────────────────────────────────────
    for sheet_row, (zone_name, building_id) in _ZONE_ROWS.items():
        col_a = ws.cell(sheet_row, 1).value or ""

        # Emergency key box code: "Boite à code: XXXX"
        m = re.search(r"Boite\s+[aà]\s+code\s*:\s*(\d+)", col_a, re.IGNORECASE)
        if m:
            rows.append({
                "building_id":  building_id,
                "zone_name":    zone_name,
                "code_type":    "emergency_key_box",
                "code_value":   m.group(1).strip(),
                "source_row":   sheet_row,
            })
        else:
            # Lebourgneuf (R45) mentions global code 2018 via reference, not explicitly.
            # Use the global emergency_key_box code confirmed in R4.
            global_box = next(
                (r["code_value"] for r in rows
                 if r["code_type"] == "key_box_transition"),
                None,
            )
            # The emergency box code is documented as 2018 in R4's "Boites à clés urgence: Code 2018"
            m2 = re.search(r"urgence.*?Code\s+(\d+)", ws.cell(4, 2).value or "", re.IGNORECASE)
            if m2:
                rows.append({
                    "building_id":  building_id,
                    "zone_name":    zone_name,
                    "code_type":    "emergency_key_box",
                    "code_value":   m2.group(1).strip(),
                    "source_row":   4,  # derived from R4 reference
                })

        # Keyless entry code (only Lebourgneuf R45 has this explicitly)
        m_kl = re.search(r"keyless\s+code\s+(?:pour\s+entrer\s+)?(\d+)", col_a, re.IGNORECASE)
        if not m_kl:
            m_kl = re.search(r"code\s+(\d{5})", col_a, re.IGNORECASE)
        if m_kl:
            rows.append({
                "building_id":  building_id,
                "zone_name":    zone_name,
                "code_type":    "keyless_entry",
                "code_value":   m_kl.group(1).strip(),
                "source_row":   sheet_row,
            })

    return rows


def run(dry_run: bool = True) -> None:
    ws   = _fetch_ws()
    rows = _parse_rows(ws)

    print(f"\n=== emergency_access_code {'DRY RUN' if dry_run else 'WRITE'} ===")
    print(f"\n  Rows to insert: {len(rows)}")
    print()
    for r in rows:
        code_display = "[populated]" if r["code_value"] else "[null]"
        print(f"  R{r['source_row']:>2}  zone={str(r['zone_name']):<26}  "
              f"building={str(r['building_id']):<5}  "
              f"type={r['code_type']:<30}  value={code_display}")

    if dry_run:
        print("\n  DRY RUN — pass --write to commit.")
        return

    # ── Write ──────────────────────────────────────────────────────────────────
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("SELECT COALESCE(MAX(access_code_id), 0) FROM emergency_access_code")
        code_next = cur.fetchone()[0] + 1
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_next = cur.fetchone()[0] + 1

        # Assign IDs manually (no sequence on this table)
        for r in rows:
            r["access_code_id"] = code_next
            code_next += 1

        execute_values(
            cur,
            """INSERT INTO emergency_access_code
               (access_code_id, building_id, zone_name, code_type, code_value)
               VALUES %s ON CONFLICT DO NOTHING""",
            [(r["access_code_id"], r["building_id"], r["zone_name"], r["code_type"], r["code_value"])
             for r in rows],
        )
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM emergency_access_code")
        total = cur.fetchone()[0]

        inserted_map = {(r["building_id"], r["zone_name"], r["code_type"]): r["access_code_id"]
                        for r in rows}

        prov = []
        for row in rows:
            pk = inserted_map.get((row["building_id"], row["zone_name"], row["code_type"]))
            if pk is None:
                continue
            for col, raw_v, ing_v in [
                ("building_id",  str(row["building_id"]) if row["building_id"] else None,
                                 str(row["building_id"]) if row["building_id"] else None),
                ("zone_name",    row["zone_name"], row["zone_name"]),
                ("code_type",    row["code_type"], row["code_type"]),
                ("code_value",   "[REDACTED-SENSITIVE]", "[REDACTED-SENSITIVE]"),
            ]:
                prov.append((
                    prov_next,
                    "emergency_access_code", pk, col,
                    "google_sheets", _DRIVE_ID, _SOURCE, _TAB,
                    row["source_row"], None,
                    raw_v, ing_v, None,
                ))
                prov_next += 1

        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov, page_size=200,
        )
        conn.commit()

        print(f"\n  emergency_access_code: {total} total rows")
        print(f"  Provenance rows written: {len(prov)}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
