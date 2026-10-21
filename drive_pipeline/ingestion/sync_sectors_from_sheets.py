"""
sync_sectors_from_sheets.py — Backfill employee sectors + building territories
from the two live Google Sheets (no François pass required).

Sources:
  - RENSEIGNEMENTS … Employé (e)  → employee.sector_id + multi-sector A5 rows
  - Table Fondamentale             → building.sector_id (fixes Inconnu)

Rules:
  - Sheet blank Secteur(s) → leave employee.sector_id unchanged (do not clear).
  - One mappable sector   → set employee.sector_id.
  - Two+ mappable sectors → leave sector_id null; ensure employee_building_assignment
    for every building in those territories (SV, MACH).
  - TF match is by Nom Unique d'Immeuble == building.adresse.

Run:
    uv run python -m drive_pipeline.ingestion.sync_sectors_from_sheets          # dry
    uv run python -m drive_pipeline.ingestion.sync_sectors_from_sheets --write  # local
    uv run python -m drive_pipeline.ingestion.sync_sectors_from_sheets --write --remote
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

_RENSEIGNEMENTS_ID = "1aTo6LhhdH60j52cCh91scmQAsiEHgImxwaWbcDARdgU"
_RENSEIGNEMENTS_TAB = "Employé (e)"
_TF_ID = "1776VvxgPCtlSzXS238A6sdLjXQ0wG3Qdlf3Fy9dk5SE"
_TF_TAB = "Liste des Projets et Immeubles"

# Sheet label fragments → DB sector.territoire (sector_id resolved at runtime).
# Order matters: first match wins for a single cell string.
_LABEL_TO_TERRITOIRE = (
    ("beauport", "Quebec-Est"),
    ("charlebourg", "Quebec-Est"),  # sheet typo Charlebourg
    ("charlesbourg", "Quebec-Est"),
    ("haute ville", "Haute-Ville"),
    ("haute-ville", "Haute-Ville"),
    ("lebourgneuf", "Quebec-Ouest"),
    ("vanier", "Quebec-Ouest"),
    ("vert basilic", "Quebec-Ouest"),
    ("ste-foy", "Sainte-Foy"),
    ("sainte-foy", "Sainte-Foy"),
    ("bleu paon", "Sainte-Foy"),
    ("orange", "Levis-Est"),  # calendar Lévis → primary Est; Ouest via A5 expand
    ("lévis", "Levis-Est"),
    ("levis", "Levis-Est"),
    ("limoilou", "Quebec-Est"),
    ("quebec-est", "Quebec-Est"),
    ("quebec-ouest", "Quebec-Ouest"),
)

# When sheet says Lévis/orange, cover BOTH Lévis DB sectors via building assignment.
_LEVIS_BOTH = ("Levis-Est", "Levis-Ouest")


def _sheets():
    token = ROOT / "token_sheets.json"
    if not token.exists():
        raise SystemExit("token_sheets.json missing — re-auth sheets readonly first")
    return build("sheets", "v4", credentials=Credentials.from_authorized_user_file(token))


def _conn(remote: bool):
    import psycopg2
    if remote:
        from drive_pipeline.ingestion.db import get_conn
        return get_conn()
    return psycopg2.connect(
        host=os.environ.get("LOCAL_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("LOCAL_DB_PORT", "54322")),
        user=os.environ.get("LOCAL_DB_USER", "postgres"),
        password=os.environ.get("LOCAL_DB_PASSWORD", "postgres"),
        dbname=os.environ.get("LOCAL_DB_NAME", "postgres"),
    )


def _map_label(raw: str) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().lower()
    if not s or s.startswith("voir ") or s == "see cleaning info":
        return None
    for needle, terr in _LABEL_TO_TERRITOIRE:
        if needle in s:
            return terr
    return None


def _expand_territories(labels: list[str]) -> list[str]:
    out: list[str] = []
    for lab in labels:
        if lab == "Levis-Est":
            for t in _LEVIS_BOTH:
                if t not in out:
                    out.append(t)
        elif lab not in out:
            out.append(lab)
    return out


def fetch_employee_sectors(svc) -> dict[str, list[str]]:
    data = svc.spreadsheets().values().get(
        spreadsheetId=_RENSEIGNEMENTS_ID,
        range=f"'{_RENSEIGNEMENTS_TAB}'",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    rows = data.get("values", [])
    out: dict[str, list[str]] = {}
    for r in rows[1:]:
        r = list(r) + [""] * max(0, 12 - len(r))
        init = str(r[0] or "").strip()
        if not init:
            continue
        mapped = []
        for cell in (r[10], r[11]):
            t = _map_label(cell)
            if t and t not in mapped:
                mapped.append(t)
        out[init] = _expand_territories(mapped)
    return out


def fetch_tf_building_territory(svc) -> dict[str, str]:
    data = svc.spreadsheets().values().get(
        spreadsheetId=_TF_ID,
        range=f"'{_TF_TAB}'!A:G",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    out: dict[str, str] = {}
    for r in data.get("values", [])[1:]:
        if len(r) < 7:
            continue
        terr = str(r[0] or "").strip()
        name = str(r[6] or "").strip()
        if terr and name and name.upper() != "N/A":
            out[name] = terr
    return out


def plan_and_apply(conn, emp_sectors: dict[str, list[str]], tf_map: dict[str, str], write: bool):
    cur = conn.cursor()
    cur.execute("SELECT sector_id, territoire FROM sector")
    terr_to_id = {t: sid for sid, t in cur.fetchall()}
    print("sector map:", terr_to_id)

    cur.execute("SELECT employee_id, initials, sector_id FROM employee WHERE initials IS NOT NULL")
    employees = {init: (eid, sid) for eid, init, sid in cur.fetchall()}

    emp_set: list[tuple[int, int, str]] = []   # (new_sid, eid, initials)
    emp_clear: list[tuple[int, str]] = []      # (eid, initials)
    multi_assigns: list[tuple[str, list[str]]] = []

    for init, terrs in sorted(emp_sectors.items()):
        if init not in employees:
            if terrs:
                print(f"  SKIP unknown employee {init}: {terrs}")
            continue
        eid, cur_sid = employees[init]
        if not terrs:
            continue
        if len(terrs) == 1:
            new_sid = terr_to_id.get(terrs[0])
            if new_sid is None:
                print(f"  SKIP {init}: unknown territory {terrs[0]!r}")
                continue
            if cur_sid != new_sid:
                emp_set.append((new_sid, eid, init))
        else:
            multi_assigns.append((init, terrs))
            if cur_sid is not None:
                print(f"  NOTE {init}: multi-sector {terrs} — will null sector_id (was {cur_sid})")
                emp_clear.append((eid, init))

    print(f"\nEmployee sector_id SET ({len(emp_set)}):")
    for sid, eid, init in emp_set:
        print(f"  {init}: → {sid}")
    print(f"Employee sector_id CLEAR for multi ({len(emp_clear)}):")
    for eid, init in emp_clear:
        print(f"  {init}: → NULL")

    # Building territory from TF
    cur.execute("SELECT building_id, adresse, sector_id FROM building")
    buildings = cur.fetchall()
    bldg_updates: list[tuple[int, int, str, int | None]] = []
    for bid, adresse, sid in buildings:
        terr = tf_map.get(adresse or "")
        if not terr:
            continue
        new_sid = terr_to_id.get(terr)
        if new_sid is None:
            continue
        if sid != new_sid:
            bldg_updates.append((bid, new_sid, adresse, sid))

    print(f"\nBuilding sector_id updates ({len(bldg_updates)}):")
    for bid, new_sid, adresse, old in bldg_updates[:30]:
        print(f"  b{bid} {adresse!r}: {old} → {new_sid}")
    if len(bldg_updates) > 30:
        print(f"  ... +{len(bldg_updates)-30} more")

    # Multi-sector building assignments
    assign_rows: list[tuple[int, int, str, str]] = []
    for init, terrs in multi_assigns:
        eid = employees[init][0]
        sids = [terr_to_id[t] for t in terrs if t in terr_to_id]
        cur.execute(
            "SELECT building_id FROM building WHERE sector_id = ANY(%s)",
            (sids,),
        )
        bids = [r[0] for r in cur.fetchall()]
        notes = f"sync_sectors_from_sheets: {', '.join(terrs)}"
        for bid in bids:
            assign_rows.append((eid, bid, "a5_territory", notes))
        print(f"\n  {init} multi → {len(bids)} buildings in {terrs}")

    if not write:
        print("\nDry run — pass --write to apply.")
        return

    for sid, eid, init in emp_set:
        cur.execute(
            "UPDATE employee SET sector_id = %s WHERE employee_id = %s",
            (sid, eid),
        )
    for eid, init in emp_clear:
        cur.execute(
            "UPDATE employee SET sector_id = NULL WHERE employee_id = %s",
            (eid,),
        )
    for bid, new_sid, adresse, old in bldg_updates:
        cur.execute(
            "UPDATE building SET sector_id = %s WHERE building_id = %s",
            (new_sid, bid),
        )
    if assign_rows:
        from psycopg2.extras import execute_values
        execute_values(
            cur,
            """INSERT INTO employee_building_assignment
               (employee_id, building_id, assignment_type, notes)
               VALUES %s
               ON CONFLICT (employee_id, building_id) DO UPDATE
               SET assignment_type = EXCLUDED.assignment_type,
                   notes = EXCLUDED.notes""",
            assign_rows,
            page_size=200,
        )

    conn.commit()
    print(f"\nCommitted: {len(emp_set)} emp set, {len(emp_clear)} emp cleared, "
          f"{len(bldg_updates)} buildings, {len(assign_rows)} assignments.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--remote", action="store_true", help="Write to remote Supabase (default: local :54322)")
    args = ap.parse_args()

    svc = _sheets()
    print("Fetching RENSEIGNEMENTS Employé (e)…")
    emp_sectors = fetch_employee_sectors(svc)
    filled = {k: v for k, v in emp_sectors.items() if v}
    print(f"  {len(filled)} employees with mapped sector(s)")
    for k, v in sorted(filled.items()):
        print(f"    {k}: {v}")

    print("\nFetching Table Fondamentale…")
    tf_map = fetch_tf_building_territory(svc)
    print(f"  {len(tf_map)} buildings with Territoire SIB")

    conn = _conn(args.remote)
    try:
        plan_and_apply(conn, emp_sectors, tf_map, args.write)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
