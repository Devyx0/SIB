"""
ingest_equipment.py — Dry-run and write ingestion of equipment rows from Boilers_EN.xlsx.

Each Boilers source row splits into 2 equipment rows:
  equipment_type='heating'  (columns 21-32)
  equipment_type='dhw'      (columns 33-44)

Run:
    uv run python -m drive_pipeline.ingestion.ingest_equipment          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_equipment --write  # write
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.ingest_vendor_contact import _norm_key
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

_BOILERS_PATH = ROOT / "work/dryrun_maintenance/Boilers_EN.xlsx"
_SHEET        = "Entretien - ChaudièresFournaise"
_SOURCE_FILE  = "Boilers_EN.xlsx"
_SKIP_CONTRACTORS = {"to be determined", "n/a"}
# Strip city suffix (", Québec", ", Lévis", etc.) then extract first civic + rest as street
_CITY_RE  = re.compile(r",\s*(?:Québec|Lévis|Charny|Loretteville)\b.*", re.IGNORECASE)
_CIVIC_RE = re.compile(r"^(\d+)(?:[-,\s]+\d+)*\s+(.*)")


def _v(val) -> str | None:
    s = str(val).strip() if val is not None else ""
    return s or None


def _parse_address(raw: str) -> tuple[str | None, str | None]:
    s = raw.split(" / ")[0]
    s = _CITY_RE.sub("", s).strip()
    m = _CIVIC_RE.match(s)
    return (m.group(1), m.group(2).strip()) if m else (None, None)


def _parse_int(val) -> int | None:
    if val is None:
        return None
    m = re.search(r"\d+", str(val))
    return int(m.group()) if m else None


def _parse_date(val) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def _load_buildings(conn) -> dict[str, int]:
    cur = conn.cursor()
    cur.execute("SELECT adresse, building_id FROM building")
    return {row[0]: row[1] for row in cur.fetchall()}


def _load_vendors(conn) -> dict[str, int]:
    cur = conn.cursor()
    cur.execute("SELECT vendor_id, nom FROM vendor_contact")
    return {_norm_key(nom): vid for vid, nom in cur.fetchall()}


def _resolve_building(raw_addr: str, live_bldg: dict[str, int]) -> int | None:
    civic, street = _parse_address(raw_addr)
    if not street or not civic:
        return None
    tf_row = _match_building(street, civic, None)
    if tf_row:
        return live_bldg.get(tf_row.get("unique_building_name"))
    # Try each civic number from the raw address (handles "313-315-317" where TF starts at 315)
    for c in re.findall(r"\d+", raw_addr.split(",")[0].split("/")[0])[1:]:
        tf_row = _match_building(street, c, None)
        if tf_row:
            return live_bldg.get(tf_row.get("unique_building_name"))
    return None


def _collect(live_bldg: dict[str, int], live_vendors: dict[str, int]):
    rows, unmatched, vendor_miss = [], [], []
    wb = openpyxl.load_workbook(str(_BOILERS_PATH), read_only=True, data_only=True)
    ws = wb[_SHEET]

    for sheet_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        raw_addr = _v(row[2])
        if not raw_addr:
            continue

        building_id = _resolve_building(raw_addr, live_bldg)
        if building_id is None:
            unmatched.append((sheet_row, raw_addr))

        contractor = _v(row[10])
        assigned_vendor_id = None
        if contractor and contractor.lower() not in _SKIP_CONTRACTORS:
            nk = _norm_key(contractor)
            assigned_vendor_id = live_vendors.get(nk)
            if assigned_vendor_id is None:
                vendor_miss.append((sheet_row, contractor))

        shared = dict(
            building_id=building_id,
            assigned_vendor_id=assigned_vendor_id,
            maintenance_frequency=_v(row[11]),
            last_maintenance_date=_parse_date(row[12]),
            next_maintenance_date=_parse_date(row[13]),
            maintenance_status=_v(row[14]),
            maintenance_note=_v(row[15]),
            urgency=_v(row[16]),
            criticality=_v(row[17]),
            action_priority=_v(row[18]),
            device_condition=_v(row[19]),
            replacement_priority=_v(row[20]),
            _sheet_row=sheet_row,
            _raw_addr=raw_addr,
            _contractor=contractor,
        )

        serial_h = _v(row[27])
        rows.append({**shared,
            "equipment_type": "heating",
            "service_area": _v(row[21]),
            "component":    _v(row[23]),
            "quantity":     _parse_int(row[24]),
            "make":         _v(row[25]),
            "model":        _v(row[26]),
            "notes":        f"Serial: {serial_h}" if serial_h else None,
            "power":        _v(row[28]),
            "efficiency":   _v(row[29]),
            "power_source": _v(row[30]),
            "energy_supplier": _v(row[31]),
            "install_year": _parse_int(row[32]),
        })

        serial_d  = _v(row[39])
        conn_note = _v(row[44]) if len(row) > 44 else None
        note_parts = (["Serial: " + serial_d] if serial_d else []) + \
                     ([f"Connection to heating: {conn_note}"] if conn_note else [])
        rows.append({**shared,
            "equipment_type": "dhw",
            "service_area": _v(row[33]),
            "component":    _v(row[35]),
            "quantity":     _parse_int(row[36]),
            "make":         _v(row[37]),
            "model":        _v(row[38]),
            "notes":        "; ".join(note_parts) or None,
            "power":        _v(row[40]),
            "efficiency":   _v(row[41]),
            "power_source": _v(row[42]),
            "energy_supplier": _v(row[43]),
            "install_year": None,
        })

    wb.close()
    return rows, unmatched, vendor_miss


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    live_bldg   = _load_buildings(conn)
    live_vendors = _load_vendors(conn)
    conn.close()

    rows, unmatched, vendor_miss = _collect(live_bldg, live_vendors)
    n_src = sum(1 for r in rows if r["equipment_type"] == "heating")

    print("\n=== equipment dry run ===")
    print(f"Source rows processed: {n_src}")
    print(f"Equipment rows planned: {len(rows)} ({n_src} heating + {len(rows) - n_src} dhw)")

    print(f"\nBuilding matches: {n_src - len(unmatched)}/{n_src} matched")
    for sr, addr in unmatched:
        print(f"  UNMATCHED row {sr}: {addr!r}")

    print(f"\nVendor matches: {n_src - len(vendor_miss)}/{n_src} resolved")
    for sr, name in vendor_miss:
        print(f"  UNRESOLVED row {sr}: {name!r}")

    print("\nSample (first 5 heating rows):")
    for r in [x for x in rows if x["equipment_type"] == "heating"][:5]:
        print(f"  bldg={r['building_id']} make={r['make']!r} model={r['model']!r} "
              f"component={r['component']!r} vendor_id={r['assigned_vendor_id']}")

    if dry_run:
        print(f"\nDRY RUN — {len(rows)} equipment rows. Pass --write to commit.")
        return

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(equipment_id), 0) FROM equipment")
        eid_start = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        equipment_vals, all_prov = [], []
        for i, r in enumerate(rows, start=1):
            eid = eid_start + i
            equipment_vals.append((
                eid, r["building_id"], None, r["equipment_type"],
                r.get("make"), r.get("model"), r.get("install_year"),
                None, None,   # seasonal shutdown/restart
                None,         # maintained_by_vendor_id
                r.get("notes"),
                r["criticality"], r["assigned_vendor_id"],
                r["maintenance_frequency"], r["last_maintenance_date"],
                r["next_maintenance_date"], r["maintenance_status"],
                r["maintenance_note"], r["urgency"], r["action_priority"],
                r["device_condition"], r["replacement_priority"],
                r.get("service_area"), r.get("component"), r.get("quantity"),
                r.get("power"), r.get("efficiency"), r.get("power_source"),
                r.get("energy_supplier"),
            ))
            sr = r["_sheet_row"]
            for col, raw, ingested in [
                ("building_id",       r["_raw_addr"],     str(r["building_id"])),
                ("equipment_type",    r["equipment_type"],r["equipment_type"]),
                ("make",              r.get("make"),      r.get("make")),
                ("component",         r.get("component"), r.get("component")),
                ("assigned_vendor_id",r["_contractor"],   str(r["assigned_vendor_id"])),
            ]:
                all_prov.append((
                    None, "equipment", eid, col,
                    "spreadsheet", None, _SOURCE_FILE, _SHEET,
                    sr, col, raw, ingested, None,
                ))

        execute_values(
            cur,
            """INSERT INTO equipment (
                equipment_id, building_id, unit_id, equipment_type,
                make, model, install_year,
                seasonal_shutdown_date, seasonal_restart_date,
                maintained_by_vendor_id, notes,
                criticality, assigned_vendor_id,
                maintenance_frequency, last_maintenance_date, next_maintenance_date,
                maintenance_status, maintenance_note, urgency, action_priority,
                device_condition, replacement_priority,
                service_area, component, quantity,
                power, efficiency, power_source, energy_supplier
            ) VALUES %s""",
            equipment_vals, page_size=500,
        )

        for start in range(0, len(all_prov), 5000):
            chunk = all_prov[start:start + 5000]
            execute_values(
                cur,
                """INSERT INTO data_provenance
                   (provenance_id, target_table, target_pk, target_column,
                    source_type, source_drive_id, source_file_name, source_tab,
                    source_row, source_column, raw_value, ingested_value, ingested_at)
                   VALUES %s""",
                [(prov_offset + start + j + 1,
                  r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12])
                 for j, r in enumerate(chunk)],
                page_size=5000,
            )

        conn.commit()
        print(f"Committed: {len(equipment_vals)} equipment rows, {len(all_prov)} provenance rows.")
        cur.execute("SELECT COUNT(*) FROM equipment")
        print(f"equipment total: {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
