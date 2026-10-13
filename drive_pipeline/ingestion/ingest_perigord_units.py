"""
ingest_perigord_units.py — Targeted insert for 1580 Perigord units, leases, tenants.

Reads the same MRR file as ingest_units_leases_tenants.py but filters to only
Perigord unit_keys. Inserts new rows starting from the current max IDs — does
NOT truncate any existing tables.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_perigord_units          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_perigord_units --write
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.provenance import log_provenance, flush, flush_to_db
from drive_pipeline.ingestion.ingest_units_leases_tenants import (
    SHEET, SOURCE_TYPE, SOURCE_FILE,
    _load_rent_roll, _load_live_buildings, _dedupe_people,
    _is_placeholder_name, _v, _num, _as_date, _month_date, _pet_bool,
    _parse_parking, _parse_storage, _parse_appliances,
)

_BUILDING_ID = 180  # 1580 Perigord
_BUILDING_ADDR = "1580, rue du Périgord"


def run(dry_run: bool = True) -> None:
    print("Loading Rent Roll…")
    headers, rows_by_unit, _ = _load_rent_roll()

    # Filter to Perigord unit_keys only
    perig_keys = {k for k in rows_by_unit
                  if "perigord" in k.lower() or "périgord" in k.lower()}
    rows_by_unit = {k: rows_by_unit[k] for k in perig_keys}
    print(f"Perigord unit keys: {len(rows_by_unit)}")

    conn = get_conn()
    cur = conn.cursor()

    # Verify building exists
    cur.execute("SELECT building_id FROM building WHERE building_id = %s", (_BUILDING_ID,))
    assert cur.fetchone(), f"Building {_BUILDING_ID} not in DB — run Task D first"

    # Verify no units already exist for this building
    cur.execute("SELECT COUNT(*) FROM unit WHERE building_id = %s", (_BUILDING_ID,))
    existing_count = cur.fetchone()[0]
    if existing_count > 0:
        print(f"ERROR: {existing_count} units already exist for building {_BUILDING_ID}. Aborting.")
        conn.close()
        return

    # Starting IDs: max + 1
    for tbl, col in [("unit", "unit_id"), ("lease", "lease_id"),
                     ("tenant", "tenant_id"), ("tenancy_record", "tenancy_id"),
                     ("guarantor", "guarantor_id"),
                     ("parking_assignment", "parking_id"),
                     ("storage_assignment", "storage_id"),
                     ("unit_appliance", "unit_appliance_id")]:
        cur.execute(f"SELECT COALESCE(MAX({col}), 0) FROM {tbl}")
        globals()[f"_start_{col}"] = cur.fetchone()[0] + 1

    unit_id     = _start_unit_id
    lease_id    = _start_lease_id
    tenant_id   = _start_tenant_id
    tenancy_id  = _start_tenancy_id
    guarantor_id = _start_guarantor_id
    parking_id  = _start_parking_id
    storage_id  = _start_storage_id
    appliance_id = _start_unit_appliance_id

    # Load existing tenants to dedup against
    cur.execute("SELECT tenant_id, nom_complet, telephone, courriel FROM tenant")
    existing_tenants: dict[tuple, int] = {}
    for tid, name, phone, email in cur.fetchall():
        existing_tenants[(name, phone, email)] = tid

    # Phase 1: collect people from Perigord rows
    all_appearances = []
    for unit_key, unit_rows in rows_by_unit.items():
        for sheet_row, row in unit_rows:
            name = _v(row[4])
            if not name or _is_placeholder_name(name):
                continue
            all_appearances.append({
                "name": name, "phone": _v(row[5]), "email": _v(row[6]),
                "phone_intl": _v(row[7]), "city": _v(row[55]) if len(row) > 55 else None,
                "postal": _v(row[56]) if len(row) > 56 else None,
                "make_info": _v(row[8]), "sheet_row": sheet_row,
                "role_label": f"tenant:{unit_key}",
            })
        for sheet_row, row in unit_rows:
            gname = _v(row[52]) if len(row) > 52 else None
            if not gname or gname.upper() in ("N/A", "NA", "NONE"):
                continue
            if _is_placeholder_name(gname):
                break
            all_appearances.append({
                "name": gname, "phone": _v(row[53]) if len(row) > 53 else None,
                "email": _v(row[54]) if len(row) > 54 else None,
                "phone_intl": None, "city": None, "postal": None,
                "make_info": None, "sheet_row": sheet_row,
                "role_label": f"guarantor:{unit_key}",
            })
            break

    raw_to_tid, tid_to_data, _ = _dedupe_people(all_appearances)

    # Remap tid_to_data so new tenant_ids start from tenant_id (not from 1)
    # _dedupe_people returns 1-based internal IDs; we need to shift them
    base_tid = tenant_id - 1  # e.g. if tenant_id=6091, base=6090, so local 1 → 6091
    raw_to_tid = {k: v + base_tid for k, v in raw_to_tid.items()}
    tid_to_data = {k + base_tid: v for k, v in tid_to_data.items()}

    # Phase 2: build records
    units, leases, tenants_new, tenancy_records = [], [], [], []
    guarantors, parking_rows, storage_rows, appliance_rows = [], [], [], []

    for unit_key, unit_rows in rows_by_unit.items():
        first_sheet_row, first_row = unit_rows[0]

        uid = unit_id; unit_id += 1
        units.append({
            "unit_id": uid, "building_id": _BUILDING_ID,
            "rue": _v(first_row[2]), "numero_appartement": _v(first_row[3]),
            "grandeur": _v(first_row[9]), "src_row": first_sheet_row,
        })
        log_provenance("unit", uid, "building_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                       str(first_sheet_row), "building", str(_BUILDING_ID), str(_BUILDING_ID))
        if _v(first_row[2]):
            log_provenance("unit", uid, "rue", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[2], _v(first_row[2]), _v(first_row[2]))
        if _v(first_row[3]):
            log_provenance("unit", uid, "numero_appartement", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[3], _v(first_row[3]), _v(first_row[3]))
        if _v(first_row[9]):
            log_provenance("unit", uid, "grandeur", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[9], _v(first_row[9]), _v(first_row[9]))

        lid = lease_id; lease_id += 1
        pet_raw = _v(first_row[70]) if len(first_row) > 70 else None
        leases.append({
            "lease_id": lid, "unit_id": uid,
            "mois": _month_date(_v(first_row[0])),
            "debut_bail": _as_date(first_row[74]) if len(first_row) > 74 else None,
            "fin_bail": _as_date(first_row[11]),
            "date_fin_confirmee": _as_date(first_row[12]),
            "date_limite_preavis": _as_date(first_row[10]),
            "statut": _v(first_row[78]) if len(first_row) > 78 else None,
            "langue_bail": _v(first_row[69]) if len(first_row) > 69 else None,
            "droit_animaux": _pet_bool(pet_raw),
            "depot": _num(first_row[15]),
            "loyer_de_base": _num(first_row[16]),
            "loyer_total": _num(first_row[49]) if len(first_row) > 49 else None,
            "mode_paiement_habituel": _v(first_row[13]),
            "somme_due_restante": _num(first_row[51]) if len(first_row) > 51 else None,
            "notes_collecte": _v(first_row[14]),
            "src_row": first_sheet_row,
        })

        for sheet_row, row in unit_rows:
            name = _v(row[4]); phone = _v(row[5]); email = _v(row[6])
            if not name or _is_placeholder_name(name):
                continue
            tid = raw_to_tid.get((name, phone, email))
            if tid is None:
                continue
            tenancy_records.append({
                "tenancy_id": tenancy_id, "lease_id": lid, "tenant_id": tid,
                "capacite": "named_on_lease", "src_row": sheet_row,
            })
            log_provenance("tenancy_record", tenancy_id, "tenant_id", SOURCE_TYPE, None,
                           SOURCE_FILE, SHEET, str(sheet_row), headers[4], name, str(tid))
            log_provenance("tenancy_record", tenancy_id, "lease_id", SOURCE_TYPE, None,
                           SOURCE_FILE, SHEET, str(sheet_row), headers[4], name, str(lid))
            tenancy_id += 1

        for sheet_row, row in unit_rows:
            gname = _v(row[52]) if len(row) > 52 else None
            if not gname or gname.upper() in ("N/A", "NA", "NONE"):
                continue
            gphone = _v(row[53]) if len(row) > 53 else None
            gemail = _v(row[54]) if len(row) > 54 else None
            gtid = raw_to_tid.get((gname, gphone, gemail))
            if gtid is None:
                break
            guarantors.append({
                "guarantor_id": guarantor_id, "lease_id": lid, "tenant_id": gtid,
                "src_row": sheet_row,
            })
            guarantor_id += 1
            break

        parking_rows += [{"lease_id": lid, **p, "parking_id": (parking_id := parking_id + 1) - 1}
                         for p in _parse_parking(first_row, headers)]
        storage_rows += [{"lease_id": lid, **s, "storage_id": (storage_id := storage_id + 1) - 1}
                         for s in _parse_storage(first_row, headers)]
        appliance_rows += [{"lease_id": lid, **a, "unit_appliance_id": (appliance_id := appliance_id + 1) - 1}
                           for a in _parse_appliances(first_row, headers)]

    # Build new tenants list
    for tid, data in sorted(tid_to_data.items()):
        tenants_new.append({
            "tenant_id": tid,
            "nom_complet": data["nom_complet"], "telephone": data["telephone"],
            "courriel": data["courriel"], "telephone_international": data["telephone_international"],
            "ville": data["ville"], "code_postal": data["code_postal"],
            "informations_pour_make": data["informations_pour_make"],
        })

    print(f"\nDry run summary:")
    print(f"  units:           {len(units)}")
    print(f"  leases:          {len(leases)}")
    print(f"  new tenants:     {len(tenants_new)} (IDs {_start_tenant_id}–{tenant_id - 1})")
    print(f"  tenancy_records: {len(tenancy_records)}")
    print(f"  guarantors:      {len(guarantors)}")
    print(f"  parking:         {len(parking_rows)}")
    print(f"  storage:         {len(storage_rows)}")
    print(f"  appliances:      {len(appliance_rows)}")
    print(f"\nSample units:")
    for u in units[:5]:
        print(f"  unit_id={u['unit_id']} apt={u['numero_appartement']!r} size={u['grandeur']!r}")

    if dry_run:
        print("\nDRY RUN — pass --write to commit")
        conn.close()
        return

    # Write
    for u in units:
        cur.execute("""INSERT INTO unit (unit_id, building_id, rue, numero_appartement, grandeur)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (u["unit_id"], u["building_id"], u["rue"], u["numero_appartement"], u["grandeur"]))

    for t in tenants_new:
        cur.execute("""INSERT INTO tenant (tenant_id, nom_complet, telephone, courriel,
                           telephone_international, ville, code_postal, informations_pour_make)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (t["tenant_id"], t["nom_complet"], t["telephone"], t["courriel"],
                     t["telephone_international"], t["ville"], t["code_postal"], t["informations_pour_make"]))

    for l in leases:
        cur.execute("""INSERT INTO lease (lease_id, unit_id, mois, debut_bail, fin_bail,
                           date_fin_confirmee, date_limite_preavis, statut, langue_bail,
                           droit_animaux, depot, loyer_de_base, loyer_total,
                           mode_paiement_habituel, somme_due_restante, notes_collecte)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (l["lease_id"], l["unit_id"], l["mois"], l["debut_bail"], l["fin_bail"],
                     l["date_fin_confirmee"], l["date_limite_preavis"], l["statut"], l["langue_bail"],
                     l["droit_animaux"], l["depot"], l["loyer_de_base"], l["loyer_total"],
                     l["mode_paiement_habituel"], l["somme_due_restante"], l["notes_collecte"]))

    for tr in tenancy_records:
        cur.execute("""INSERT INTO tenancy_record (tenancy_id, lease_id, tenant_id, capacite)
                       VALUES (%s, %s, %s, %s)""",
                    (tr["tenancy_id"], tr["lease_id"], tr["tenant_id"], tr["capacite"]))

    for g in guarantors:
        cur.execute("""INSERT INTO guarantor (guarantor_id, lease_id, tenant_id)
                       VALUES (%s, %s, %s)""",
                    (g["guarantor_id"], g["lease_id"], g["tenant_id"]))

    for p in parking_rows:
        cur.execute("""INSERT INTO parking_assignment (parking_id, lease_id, mode, location_type, count, cost)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (p["parking_id"], p["lease_id"], p["mode"], p["location_type"], p["count"], p["cost"]))

    for s in storage_rows:
        cur.execute("""INSERT INTO storage_assignment (storage_id, lease_id, mode, count, cost)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (s["storage_id"], s["lease_id"], s["mode"], s["count"], s["cost"]))

    for a in appliance_rows:
        cur.execute("""INSERT INTO unit_appliance (unit_appliance_id, lease_id, item)
                       VALUES (%s, %s, %s)""",
                    (a["unit_appliance_id"], a["lease_id"], a["item"]))

    conn.commit()
    n_prov = flush_to_db(conn)
    conn.commit()

    print(f"\nCOMMITTED:")
    print(f"  {len(units)} units (IDs {_start_unit_id}–{unit_id - 1})")
    print(f"  {len(tenants_new)} tenants (IDs {_start_tenant_id}–{tenant_id - 1})")
    print(f"  {len(leases)} leases, {len(tenancy_records)} tenancy_records")
    print(f"  {len(guarantors)} guarantors, {len(parking_rows)} parking, {len(storage_rows)} storage")
    print(f"  {n_prov} provenance rows written")
    conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
