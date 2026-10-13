"""
ingest_units_leases_tenants.py — Ingestion of units, leases, and tenants from the
Master Rent Roll.

Full-replace design: unit_ids are assigned by source-file row position. Monthly
refreshes require clearing existing data first — use --refresh, not --write.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_units_leases_tenants           # dry run
    uv run python -m drive_pipeline.ingestion.ingest_units_leases_tenants --write   # write (only safe on empty tables)
    uv run python -m drive_pipeline.ingestion.ingest_units_leases_tenants --refresh # truncate + reload (monthly refresh)
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from psycopg2.extras import execute_values

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.provenance import log_provenance, flush
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

MRR_PATH = ROOT / "work/dryrun_maintenance/Master Rent Roll - All SIB Units.xlsx"
SHEET = "Rent roll"
SOURCE_TYPE = "master_rent_roll"
SOURCE_FILE = "Master Rent Roll - All SIB Units.xlsx"

# Rows to skip entirely — not real units
_SKIP_UNIT_KEYS = {"TOTAL", "Total", "RECOUVREMENT", "RECOUV"}

# Known building names not in DB — flag rows, create no units
_UNMATCHED_BUILDING_NAMES: set[str] = set()


# Tables rebuilt on every refresh — in FK dependency order (children first)
_REFRESH_TABLES = (
    "unit_appliance", "parking_assignment", "storage_assignment",
    "tenancy_record", "guarantor", "lease", "tenant", "unit",
)


def _preflight_check(refresh: bool) -> None:
    """Abort if tables are populated and --refresh was not passed; truncate if it was."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM unit")
    existing = cur.fetchone()[0]
    if existing == 0:
        conn.close()
        return
    if not refresh:
        conn.close()
        raise SystemExit(
            f"\nERROR: unit table already has {existing} rows.\n"
            "\nThis script uses a full-replace design: unit_ids are assigned by\n"
            "source-file row position. Re-inserting without clearing first fails\n"
            "immediately on unit_id=1 PK conflict.\n"
            "\nFor a monthly refresh run:\n"
            "  uv run python -m drive_pipeline.ingestion.ingest_units_leases_tenants --refresh\n"
            "\n--refresh truncates (in FK order):\n"
            f"  {', '.join(_REFRESH_TABLES)}\n"
            "plus data_provenance rows for those tables, then reloads from source.\n"
        )
    try:
        print("\nRefreshing — clearing existing data…")
        cur.execute(
            "DELETE FROM data_provenance WHERE target_table = ANY(%s)",
            (list(_REFRESH_TABLES),),
        )
        cur.execute(f"TRUNCATE {', '.join(_REFRESH_TABLES)}")
        conn.commit()
        print(f"  Cleared: {', '.join(_REFRESH_TABLES)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _is_revenue_unit(unit_key: str) -> bool:
    """True for parking slots, laundry/antenna revenue lines — not residential units."""
    uk = unit_key.upper()
    return (
        "STAT_" in uk        # STAT_41eRue-Gros-Pins_J, STAT_Osen_A13, STAT_410, STAT_860
        or "-STAT " in uk    # 135-STAT D1 Grande Allee O., 2829-STAT 1 Saint-Louis
        or "BUANDERIE" in uk # Buanderie, 254-Buanderie Saint-Jean, Buanderie et stationnements
        or "COINAMATIC" in uk# Coinamatic-cedres
        or "ROGERS" in uk    # 350-ROGERS
    )


def _is_placeholder_name(name: str) -> bool:
    """True for non-person values in the Full Name slot."""
    n = name.strip().lower()
    return (
        "vacant" in n  # VACANT, Bureau de location (VACANT), Bruno Coulombe (décédé) VACANT
        or bool(re.match(r"^(buanderie|coinamatic|communauto)", n))
        or bool(re.match(r"^location\s+du\s+stationnement", n))
        or ("rogers" in n and "antenne" in n)
    )


# ── Small helpers ─────────────────────────────────────────────────────────────

def _v(val):
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _num(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _bool_flag(val):
    return str(val).strip().lower() in ("x", "yes", "oui", "vrai", "true", "1") if val else False


def _pet_bool(val):
    """'Yes' → True; 'No' / French 'Non' starts → False; free text → True (pets allowed); None → None."""
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    if s in ("no", "non"):
        return False
    if s == "yes" or s == "oui":
        return True
    # "Non, sauf..." — technically no but with exceptions; store as True (animals present)
    if s.startswith("non"):
        return True
    return True


def _as_date(val):
    import datetime
    if val is None:
        return None
    if hasattr(val, "date"):
        return val.date()
    if isinstance(val, str):
        s = val.strip()
        if not s or s.upper() in ("N/A", "NA", "S/O", "N/D"):
            return None
        try:
            return datetime.date.fromisoformat(s)
        except ValueError:
            return None
    return None


_FR_MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}


def _month_date(val):
    """'September 2026' or 'Septembre 2026' → date(2026, 9, 1)."""
    import datetime
    if not val:
        return None
    parts = str(val).strip().split()
    if len(parts) != 2:
        return None
    month_str, year_str = parts
    try:
        year = int(year_str)
    except ValueError:
        return None
    try:
        month = datetime.datetime.strptime(month_str, "%B").month
    except ValueError:
        month = _FR_MONTHS.get(month_str.lower())
        if month is None:
            return None
    return datetime.date(year, month, 1)


# ── Person normalization and dedup ────────────────────────────────────────────

def _normalize_person(name, phone, email):
    """Return a stable dedup key. Primary: (norm_name, norm_email); secondary: (norm_name, norm_phone)."""
    def nrm(s):
        if not s:
            return ""
        s = unicodedata.normalize("NFD", str(s))
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return s.lower().strip()

    def nrm_phone(p):
        return re.sub(r"\D", "", str(p)) if p else ""

    nn = nrm(name)
    ne = nrm(email).replace(" ", "")
    np_ = nrm_phone(phone)

    if ne:
        return (nn, ne)
    if np_:
        return (nn, np_)
    return (nn, "")


def _dedupe_people(appearances):
    """
    appearances: list of dicts with keys:
        name, phone, email, phone_intl, city, postal, make_info, role_label

    Returns:
        raw_to_tid:  {(name, phone, email) → tenant_id}
        tid_to_data: {tenant_id → dict}  — first-seen data wins
        tid_to_roles: {tenant_id → [role_label]}
    """
    key_to_tid = {}
    tid_to_data = {}
    tid_to_roles = defaultdict(list)
    raw_to_tid = {}
    next_id = 1

    for i, a in enumerate(appearances):
        name, phone, email = a["name"], a["phone"], a["email"]
        norm_key = _normalize_person(name, phone, email)
        # Name-only appearances: each is a distinct person — false merge is worse than a near-dup
        if norm_key[1] == "":
            norm_key = (norm_key[0], f"__solo_{i}__")
        raw_key = (name, phone, email)

        if norm_key not in key_to_tid:
            tid = next_id
            next_id += 1
            key_to_tid[norm_key] = tid
            tid_to_data[tid] = {
                "nom_complet":             name,
                "telephone":               phone,
                "courriel":                email,
                "telephone_international": a["phone_intl"],
                "ville":                   a["city"],
                "code_postal":             a["postal"],
                "informations_pour_make":  a["make_info"],
                "first_sheet_row":         a["sheet_row"],
            }

        tid = key_to_tid[norm_key]
        raw_to_tid[raw_key] = tid
        tid_to_roles[tid].append(a["role_label"])

    return raw_to_tid, tid_to_data, tid_to_roles


# ── Sheet loading ─────────────────────────────────────────────────────────────

def _load_rent_roll():
    """
    Return (headers, rows_by_unit, stats).
    rows_by_unit: {unit_natural_key: [(sheet_row_num, row_tuple), ...]}
    """
    wb = openpyxl.load_workbook(str(MRR_PATH), read_only=True, data_only=True)
    ws = wb[SHEET]

    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]

    rows_by_unit = defaultdict(list)
    n_read = n_skip_month = n_skip_total = n_skip_revenue = 0

    for sheet_row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        month = _v(row[0])
        unit_key = _v(row[1])

        if month not in ("September 2026", "Septembre 2026"):
            n_skip_month += 1
            continue

        if not unit_key or unit_key in _SKIP_UNIT_KEYS:
            n_skip_total += 1
            continue

        # Parking slots, laundry revenue rows, antenna leases — not residential units
        if _is_revenue_unit(unit_key):
            n_skip_revenue += 1
            continue

        n_read += 1
        rows_by_unit[unit_key].append((sheet_row_num, row))

    wb.close()
    return headers, rows_by_unit, {
        "read": n_read, "skip_month": n_skip_month,
        "skip_total": n_skip_total, "skip_revenue": n_skip_revenue,
    }


def _load_live_buildings(conn):
    """Return {adresse: building_id} from live DB."""
    cur = conn.cursor()
    cur.execute("SELECT building_id, adresse FROM building")
    return {adresse: bid for bid, adresse in cur.fetchall()}


# ── Parking / storage / appliance parsers ─────────────────────────────────────

# (count_col_idx, cost_col_idx_or_None, mode, location_type)
_PARKING_COLS = [
    (19, None, "on_lease",  "exterior"),
    (20, 21,   "addendum",  "exterior"),
    (22, None, "on_lease",  "interior"),
    (23, 24,   "addendum",  "interior"),
    (25, None, "on_lease",  "covered"),
    (26, None, "on_lease",  "garage"),
    (27, 28,   "addendum",  "garage"),
    (31, 32,   "contract",  "exterior"),
    (33, 34,   "contract",  "interior"),
    (35, 36,   "contract",  "covered"),
    (37, 38,   "contract",  "garage"),
]

_STORAGE_COLS = [
    (41, None, "on_lease"),
    (42, None, "addendum"),
    (43, 44,   "contract"),
]

_APPLIANCE_COLS = [
    (57, "Stove"),
    (58, "Dishwasher"),
    (59, "Refrigerator"),
    (60, "Washer"),
    (61, "Dryer"),
    (63, "Furniture"),
]


def _parse_parking(row, headers):
    results = []
    for ci, cc, mode, loc in _PARKING_COLS:
        count = _num(row[ci])
        if not count or count <= 0:
            continue
        results.append({
            "mode": mode, "location_type": loc, "count": int(count),
            "cost": _num(row[cc]) if cc is not None else None,
            "src_col_count": headers[ci],
            "src_col_cost": headers[cc] if cc is not None else None,
        })
    return results


def _parse_storage(row, headers):
    results = []
    for ci, cc, mode in _STORAGE_COLS:
        count = _num(row[ci])
        if not count or count <= 0:
            continue
        results.append({
            "mode": mode, "count": int(count),
            "cost": _num(row[cc]) if cc is not None else None,
            "src_col_count": headers[ci],
            "src_col_cost": headers[cc] if cc is not None else None,
        })
    return results


def _parse_appliances(row, headers):
    results = []
    for ci, item in _APPLIANCE_COLS:
        if _bool_flag(row[ci]):
            results.append({"item": item, "src_col": headers[ci]})
    return results


# ── Main run ──────────────────────────────────────────────────────────────────

def run(dry_run=True, refresh=False):
    print("Loading Rent roll sheet…")
    headers, rows_by_unit, load_stats = _load_rent_roll()

    conn = get_conn()
    live_bldg = _load_live_buildings(conn)
    conn.close()

    # ── Phase 1: collect all person appearances for dedup ─────────────────────
    # We need to scan ALL rows first to build the dedup pool before assigning tenant_ids.
    all_appearances = []

    n_placeholder_filtered = 0
    for unit_key, unit_rows in rows_by_unit.items():
        for sheet_row, row in unit_rows:
            name = _v(row[4])
            if not name:
                continue
            if _is_placeholder_name(name):
                n_placeholder_filtered += 1
                continue
            all_appearances.append({
                "name": name, "phone": _v(row[5]), "email": _v(row[6]),
                "phone_intl": _v(row[7]), "city": _v(row[55]), "postal": _v(row[56]),
                "make_info": _v(row[8]), "sheet_row": sheet_row,
                "role_label": f"tenant:{unit_key}",
            })
        # Guarantor — take first row in group that has a guarantor name
        for sheet_row, row in unit_rows:
            gname = _v(row[52])
            if not gname or gname.upper() in ("N/A", "NA", "NONE"):
                continue
            if _is_placeholder_name(gname):
                n_placeholder_filtered += 1
                break
            all_appearances.append({
                "name": gname, "phone": _v(row[53]), "email": _v(row[54]),
                "phone_intl": None, "city": None, "postal": None,
                "make_info": None, "sheet_row": sheet_row,
                "role_label": f"guarantor:{unit_key}",
            })
            break  # one guarantor per unit

    n_raw_appearances = len(all_appearances)
    raw_to_tid, tid_to_data, tid_to_roles = _dedupe_people(all_appearances)
    n_distinct_tenants = len(tid_to_data)

    # ── Phase 2: build all records ────────────────────────────────────────────
    units = []
    leases = []
    tenancy_records = []
    guarantors = []
    parking_rows = []
    storage_rows = []
    appliance_rows = []

    n_unmatched_bldg = 0
    unmatched_names = defaultdict(int)

    unit_id = lease_id = tenancy_id = guarantor_id = parking_id = storage_id = appliance_id = 1

    for unit_key, unit_rows in rows_by_unit.items():
        first_sheet_row, first_row = unit_rows[0]

        bldg_name = _v(first_row[77])

        # Resolve building_id via direct adresse match
        building_id = None
        if bldg_name:
            building_id = live_bldg.get(bldg_name)
            if building_id is None and bldg_name not in _UNMATCHED_BUILDING_NAMES:
                # Fallback: parse civic+street from unit_key and try _match_building.
                # Street column (idx 2) is empty for these rows, so we attempt a rough parse.
                # ponytail: simple heuristic, covers the known gap cases
                m = re.match(r"^(\d+)[-\s]+\d+\s+(.+)$", unit_key)
                if m:
                    civic_str, street_str = m.group(1), m.group(2).rstrip(".")
                    tf_row = _match_building(street_str, civic_str, None)
                    if tf_row:
                        bldg_name_tf = tf_row.get("unique_building_name")
                        building_id = live_bldg.get(bldg_name_tf)

        if building_id is None:
            n_unmatched_bldg += 1
            unmatched_names[bldg_name or "(no building name)"] += 1
            continue  # skip unit — cannot write without building_id FK

        # ── Unit record ───────────────────────────────────────────────────────
        uid = unit_id
        unit_id += 1
        units.append({
            "unit_id": uid,
            "building_id": building_id,
            "rue": _v(first_row[2]),
            "numero_appartement": _v(first_row[3]),
            "grandeur": _v(first_row[9]),
            "src_row": first_sheet_row,
        })

        log_provenance("unit", uid, "building_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                       str(first_sheet_row), headers[77], _v(first_row[77]), str(building_id))
        if _v(first_row[2]):
            log_provenance("unit", uid, "rue", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[2], _v(first_row[2]), _v(first_row[2]))
        if _v(first_row[3]):
            log_provenance("unit", uid, "numero_appartement", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[3], _v(first_row[3]), _v(first_row[3]))
        if _v(first_row[9]):
            log_provenance("unit", uid, "grandeur", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), headers[9], _v(first_row[9]), _v(first_row[9]))

        # ── Lease record (from first row per unit) ────────────────────────────
        lid = lease_id
        lease_id += 1
        pet_raw = _v(first_row[70])
        leases.append({
            "lease_id": lid,
            "unit_id": uid,
            "mois": _month_date(_v(first_row[0])),
            "debut_bail": _as_date(first_row[74]),
            "fin_bail": _as_date(first_row[11]),
            "date_fin_confirmee": _as_date(first_row[12]),
            "date_limite_preavis": _as_date(first_row[10]),
            "statut": _v(first_row[78]),
            "langue_bail": _v(first_row[69]),
            "droit_animaux": _pet_bool(pet_raw),
            "depot": _num(first_row[15]),
            "loyer_de_base": _num(first_row[16]),
            "loyer_total": _num(first_row[49]),
            "mode_paiement_habituel": _v(first_row[13]),
            "somme_due_restante": _num(first_row[51]),
            "disponibilite_tableau_location": _v(first_row[76]),
            "notes_collecte": _v(first_row[14]),
            "src_row": first_sheet_row,
        })

        for col_name, raw_val, db_val, col_idx in [
            ("mois",                       first_row[0],  _month_date(_v(first_row[0])), 0),
            ("debut_bail",                 first_row[74], _as_date(first_row[74]),  74),
            ("fin_bail",                   first_row[11], _as_date(first_row[11]),  11),
            ("date_fin_confirmee",         first_row[12], _as_date(first_row[12]),  12),
            ("date_limite_preavis",        first_row[10], _as_date(first_row[10]),  10),
            ("statut",                     first_row[78], _v(first_row[78]),         78),
            ("langue_bail",                first_row[69], _v(first_row[69]),         69),
            ("droit_animaux",              first_row[70], _pet_bool(pet_raw),        70),
            ("depot",                      first_row[15], _num(first_row[15]),       15),
            ("loyer_de_base",              first_row[16], _num(first_row[16]),       16),
            ("loyer_total",                first_row[49], _num(first_row[49]),       49),
            ("mode_paiement_habituel",     first_row[13], _v(first_row[13]),         13),
            ("somme_due_restante",         first_row[51], _num(first_row[51]),       51),
            ("disponibilite_tableau_location", first_row[76], _v(first_row[76]),    76),
            ("notes_collecte",             first_row[14], _v(first_row[14]),         14),
        ]:
            if raw_val is not None:
                log_provenance("lease", lid, col_name, SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                               str(first_sheet_row), headers[col_idx], str(raw_val), str(db_val))

        # ── Tenancy records (one per co-tenant row) ───────────────────────────
        for sheet_row, row in unit_rows:
            name = _v(row[4])
            if not name:
                continue
            phone = _v(row[5])
            email = _v(row[6])
            tid = raw_to_tid.get((name, phone, email))
            if tid is None:
                continue

            tenancy_records.append({
                "tenancy_id": tenancy_id,
                "lease_id": lid,
                "tenant_id": tid,
                "capacite": "named_on_lease",
                "src_row": sheet_row,
            })
            log_provenance("tenancy_record", tenancy_id, "tenant_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(sheet_row), headers[4], name, str(tid))
            log_provenance("tenancy_record", tenancy_id, "lease_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(sheet_row), headers[4], name, str(lid))
            log_provenance("tenancy_record", tenancy_id, "capacite", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(sheet_row), headers[4], name, "named_on_lease")
            tenancy_id += 1

        # ── Guarantor (first row in group with a valid name) ──────────────────
        for sheet_row, row in unit_rows:
            gname = _v(row[52])
            if not gname or gname.upper() in ("N/A", "NA", "NONE"):
                continue
            gphone = _v(row[53])
            gemail = _v(row[54])
            gtid = raw_to_tid.get((gname, gphone, gemail))
            if gtid is None:
                continue
            guarantors.append({
                "guarantor_id": guarantor_id,
                "lease_id": lid,
                "tenant_id": gtid,
                "src_row": sheet_row,
            })
            log_provenance("guarantor", guarantor_id, "tenant_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(sheet_row), headers[52], gname, str(gtid))
            log_provenance("guarantor", guarantor_id, "lease_id", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(sheet_row), headers[52], gname, str(lid))
            guarantor_id += 1
            break

        # ── Parking / storage / appliances (from first row per unit) ──────────
        for p in _parse_parking(first_row, headers):
            parking_rows.append({"parking_id": parking_id, "lease_id": lid, **p, "src_row": first_sheet_row})
            log_provenance("parking_assignment", parking_id, "count", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), p["src_col_count"], str(first_row[headers.index(p["src_col_count"])]),
                           str(p["count"]))
            if p["cost"] is not None and p["src_col_cost"]:
                log_provenance("parking_assignment", parking_id, "cost", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                               str(first_sheet_row), p["src_col_cost"],
                               str(first_row[headers.index(p["src_col_cost"])]), str(p["cost"]))
            parking_id += 1

        for s in _parse_storage(first_row, headers):
            storage_rows.append({"storage_id": storage_id, "lease_id": lid, **s, "src_row": first_sheet_row})
            log_provenance("storage_assignment", storage_id, "count", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), s["src_col_count"], str(first_row[headers.index(s["src_col_count"])]),
                           str(s["count"]))
            if s["cost"] is not None and s["src_col_cost"]:
                log_provenance("storage_assignment", storage_id, "cost", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                               str(first_sheet_row), s["src_col_cost"],
                               str(first_row[headers.index(s["src_col_cost"])]), str(s["cost"]))
            storage_id += 1

        for a in _parse_appliances(first_row, headers):
            appliance_rows.append({"unit_appliance_id": appliance_id, "lease_id": lid, **a, "src_row": first_sheet_row})
            log_provenance("unit_appliance", appliance_id, "item", SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                           str(first_sheet_row), a["src_col"], str(first_row[headers.index(a["src_col"])]),
                           a["item"])
            appliance_id += 1

    prov_rows = flush()

    # ── Tenant provenance (logged once per tenant at their first appearance) ──
    # Done separately since dedup collapses many appearances to one tenant row.
    tenant_prov = []
    for tid, data in tid_to_data.items():
        sheet_row = data["first_sheet_row"]
        for col_name, col_idx, val in [
            ("nom_complet",             4,  data["nom_complet"]),
            ("telephone",               5,  data["telephone"]),
            ("courriel",                6,  data["courriel"]),
            ("telephone_international", 7,  data["telephone_international"]),
            ("ville",                   55, data["ville"]),
            ("code_postal",             56, data["code_postal"]),
            ("informations_pour_make",  8,  data["informations_pour_make"]),
        ]:
            if val:
                log_provenance("tenant", tid, col_name, SOURCE_TYPE, None, SOURCE_FILE, SHEET,
                               str(sheet_row), headers[col_idx], val, val)
    tenant_prov = flush()

    all_prov = prov_rows + tenant_prov

    # ── Dedup examples: people appearing in multiple roles ────────────────────
    multi_role = [
        (tid, tid_to_data[tid]["nom_complet"], roles)
        for tid, roles in tid_to_roles.items()
        if len(roles) > 1
    ]
    # Sort by role count desc, take first 5
    multi_role.sort(key=lambda x: -len(x[2]))
    dedup_examples = multi_role[:5]

    # ── Field coverage per table ──────────────────────────────────────────────
    def _coverage(records, fields):
        if not records:
            return {}
        return {
            f: f"{sum(1 for r in records if r.get(f) is not None) / len(records) * 100:.0f}%"
            for f in fields
        }

    # ── Print dry-run report ──────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("MASTER RENT ROLL — DRY RUN REPORT")
    print("=" * 70)

    print("\n── 1. Sheet inventory ────────────────────────────────────────────────")
    DATA_SHEETS = {
        "Rent roll": "PRIMARY DATA (used)",
    }
    SKIP_SHEETS = {
        "Revenus commerciaux": "empty",
        "Dépôts locataires": "empty",
        "Unités du Rent roll": "unit index (aggregate)",
        "Rent roll format évaluateur": "evaluator format (aggregate)",
        "Copie de Rent roll format évalu": "evaluator copy (aggregate)",
        "Rent roll format SCHL": "SCHL format (aggregate)",
        "Revenus potentiels stationnemen": "parking pricing (no PII)",
        "Revenus potentiels rangements": "storage pricing (no PII)",
    }
    print(f"  {'Rent roll':<42} PRIMARY DATA (used)")
    for name, reason in SKIP_SHEETS.items():
        print(f"  {name:<42} SKIP ({reason})")
    print(f"  (22 per-project appliance sheets)            SKIP (unit index by project)")

    print("\n── 2. Row counts ─────────────────────────────────────────────────────")
    print(f"  September/Septembre 2026 data rows:   {load_stats['read']:>6}")
    print(f"  Non-September rows skipped:           {load_stats['skip_month']:>6}  (structural: subtotals, group headers, blank)")
    print(f"  TOTAL/RECOUV aggregate rows skipped:  {load_stats['skip_total']:>6}")
    print(f"  Revenue unit rows skipped:            {load_stats['skip_revenue']:>6}  (STAT/Buanderie/Coinamatic/Rogers)")
    print(f"  Placeholder names filtered:           {n_placeholder_filtered:>6}  (VACANT/Buanderie/Communauto etc.)")
    print(f"  Distinct residential unit keys:       {len(rows_by_unit):>6}")
    print(f"  Units without building match:         {n_unmatched_bldg:>6}")
    print(f"  Units matched to building_id:         {len(units):>6}")

    print("\n── 3. Table-level counts ─────────────────────────────────────────────")
    print(f"  unit:               {len(units):>6}")
    print(f"  lease:              {len(leases):>6}")
    print(f"  tenant (distinct):  {n_distinct_tenants:>6}  (from {n_raw_appearances} raw appearances)")
    print(f"  tenancy_record:     {len(tenancy_records):>6}")
    print(f"  guarantor:          {len(guarantors):>6}")
    print(f"  parking_assignment: {len(parking_rows):>6}")
    print(f"  storage_assignment: {len(storage_rows):>6}")
    print(f"  unit_appliance:     {len(appliance_rows):>6}")
    print(f"  data_provenance:    {len(all_prov):>6}")

    print("\n── 4. Person deduplication ───────────────────────────────────────────")
    collapse = n_raw_appearances / n_distinct_tenants if n_distinct_tenants else 0
    print(f"  Raw appearances (after placeholder filter): {n_raw_appearances}")
    print(f"  Distinct people:                            {n_distinct_tenants}")
    print(f"  Collapse ratio:                             {collapse:.2f}x")
    print(f"  Name-only appearances (no phone+email):     each treated as distinct person")

    # Explicit check for the two key multi-role examples
    robichaud = [(tid, n, r) for tid, n, r in
                 [(tid, d["nom_complet"], tid_to_roles[tid]) for tid, d in tid_to_data.items()]
                 if "robichaud" in (n or "").lower() and len(r) > 1]
    carbonneau = [(tid, n, r) for tid, n, r in
                  [(tid, d["nom_complet"], tid_to_roles[tid]) for tid, d in tid_to_data.items()]
                  if "carbonneau" in (n or "").lower() and len(r) > 1]
    print(f"\n  Robichaud multi-role check: {'FOUND ✓' if robichaud else 'NOT FOUND ✗'}")
    for tid, name, roles in robichaud:
        for r in roles: print(f"    [{name}] → {r}")
    print(f"  Carbonneau multi-role check: {'FOUND ✓' if carbonneau else 'NOT FOUND ✗'}")
    for tid, name, roles in carbonneau:
        for r in roles: print(f"    [{name}] → {r}")

    if dedup_examples:
        print(f"\n  Top multi-role examples (excluding placeholder-name blowups):")
        # Skip VACANT/placeholder names that somehow made it through
        filtered_examples = [(t, n, r) for t, n, r in dedup_examples if not _is_placeholder_name(n)][:5]
        for tid, name, roles in filtered_examples:
            print(f"    tenant_id={tid}  {name!r}  ({len(roles)} roles)")
            for r in roles[:5]:
                print(f"      → {r}")
            if len(roles) > 5:
                print(f"      … ({len(roles)-5} more)")
    else:
        print("  No multi-role appearances found.")

    print("\n── 5. Building match coverage ────────────────────────────────────────")
    print(f"  Matched:   {len(units)}")
    print(f"  Unmatched: {n_unmatched_bldg}")
    if unmatched_names:
        for name, count in sorted(unmatched_names.items(), key=lambda x: -x[1]):
            print(f"    {count:>4} rows  {name!r}")

    print("\n── 6. Field coverage ─────────────────────────────────────────────────")
    unit_cov = _coverage(units, ["building_id", "rue", "numero_appartement", "grandeur"])
    print("  unit:", unit_cov)

    lease_cov = _coverage(leases, [
        "debut_bail", "fin_bail", "loyer_de_base", "loyer_total", "depot",
        "mode_paiement_habituel", "statut", "langue_bail", "droit_animaux",
        "notes_collecte", "somme_due_restante",
    ])
    print("  lease:", lease_cov)

    tenant_list = list(tid_to_data.values())
    tenant_cov = _coverage(tenant_list, [
        "nom_complet", "telephone", "courriel", "telephone_international",
        "ville", "code_postal", "informations_pour_make",
    ])
    print("  tenant:", tenant_cov)

    print("\n── 7. Flags ──────────────────────────────────────────────────────────")
    name_only = sum(
        1 for a in all_appearances
        if not _v(a.get("email")) and not re.sub(r"\D", "", str(a.get("phone") or ""))
    )
    print(f"  Name-only appearances (no phone, no email):   {name_only}  → each treated as distinct person")
    print(f"  Placeholder names filtered (not written):     {n_placeholder_filtered}")

    # Commercial/corporate tenants — kept but flagged
    _COMPANY_RE = re.compile(r"\binc\.?\b|\bltée\b|\bltee\b|québec\s+inc|s\.a\.s\b", re.IGNORECASE)
    company_tenants = {
        d["nom_complet"] for d in tid_to_data.values()
        if d["nom_complet"] and _COMPANY_RE.search(d["nom_complet"])
    }
    print(f"\n  Commercial/corporate tenant names kept (real leases, company as tenant):")
    for n in sorted(company_tenants):
        print(f"    {n!r}")

    # Guarantor rows where gname = N/A or missing
    n_no_guarantor = sum(
        1 for unit_rows in rows_by_unit.values()
        if not any(
            _v(row[52]) and _v(row[52]).upper() not in ("N/A", "NA", "NONE")
            for _, row in unit_rows
        )
    )
    print(f"  Units with no guarantor:                      {n_no_guarantor}")

    if dry_run:
        print()
        print("DRY RUN COMPLETE — nothing written to Supabase.")
        print()
        return

    _preflight_check(refresh)

    # ── Write to Supabase ─────────────────────────────────────────────────────
    print("\nWriting to Supabase…")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        execute_values(cur,
            "INSERT INTO unit (unit_id, building_id, rue, numero_appartement, grandeur) VALUES %s",
            [(u["unit_id"], u["building_id"], u["rue"], u["numero_appartement"], u["grandeur"])
             for u in units],
            page_size=2000,
        )
        print(f"  unit:               {len(units)}")

        execute_values(cur,
            "INSERT INTO tenant (tenant_id, nom_complet, telephone, courriel,"
            " telephone_international, ville, code_postal, informations_pour_make) VALUES %s",
            [(tid, d["nom_complet"], d["telephone"], d["courriel"],
              d["telephone_international"], d["ville"], d["code_postal"],
              d["informations_pour_make"])
             for tid, d in sorted(tid_to_data.items())],
            page_size=2000,
        )
        print(f"  tenant:             {len(tid_to_data)}")

        execute_values(cur,
            "INSERT INTO lease (lease_id, unit_id, mois, debut_bail, fin_bail, date_fin_confirmee,"
            " date_limite_preavis, statut, langue_bail, droit_animaux, depot, loyer_de_base,"
            " loyer_total, mode_paiement_habituel, somme_due_restante,"
            " disponibilite_tableau_location, notes_collecte) VALUES %s",
            [(l["lease_id"], l["unit_id"], l["mois"], l["debut_bail"], l["fin_bail"],
              l["date_fin_confirmee"], l["date_limite_preavis"], l["statut"],
              l["langue_bail"], l["droit_animaux"], l["depot"], l["loyer_de_base"],
              l["loyer_total"], l["mode_paiement_habituel"], l["somme_due_restante"],
              l["disponibilite_tableau_location"], l["notes_collecte"])
             for l in leases],
            page_size=2000,
        )
        print(f"  lease:              {len(leases)}")

        execute_values(cur,
            "INSERT INTO tenancy_record (tenancy_id, lease_id, tenant_id, capacite) VALUES %s",
            [(tr["tenancy_id"], tr["lease_id"], tr["tenant_id"], tr["capacite"])
             for tr in tenancy_records],
            template="(%s, %s, %s, %s::tenancy_capacity)",
            page_size=2000,
        )
        print(f"  tenancy_record:     {len(tenancy_records)}")

        execute_values(cur,
            "INSERT INTO guarantor (guarantor_id, lease_id, tenant_id) VALUES %s",
            [(g["guarantor_id"], g["lease_id"], g["tenant_id"]) for g in guarantors],
            page_size=2000,
        )
        print(f"  guarantor:          {len(guarantors)}")

        execute_values(cur,
            "INSERT INTO parking_assignment (parking_id, lease_id, mode, location_type, count, cost) VALUES %s",
            [(p["parking_id"], p["lease_id"], p["mode"], p["location_type"], p["count"], p["cost"])
             for p in parking_rows],
            page_size=2000,
        )
        print(f"  parking_assignment: {len(parking_rows)}")

        execute_values(cur,
            "INSERT INTO storage_assignment (storage_id, lease_id, mode, count, cost) VALUES %s",
            [(s["storage_id"], s["lease_id"], s["mode"], s["count"], s["cost"])
             for s in storage_rows],
            page_size=2000,
        )
        print(f"  storage_assignment: {len(storage_rows)}")

        execute_values(cur,
            "INSERT INTO unit_appliance (unit_appliance_id, lease_id, item, included) VALUES %s",
            [(a["unit_appliance_id"], a["lease_id"], a["item"], True) for a in appliance_rows],
            page_size=2000,
        )
        print(f"  unit_appliance:     {len(appliance_rows)}")

        # Provenance in 5k-row chunks — each chunk is one multi-row INSERT via execute_values
        _CHUNK = 5000
        for start in range(0, len(all_prov), _CHUNK):
            chunk = all_prov[start:start + _CHUNK]
            execute_values(cur,
                "INSERT INTO data_provenance (provenance_id, target_table, target_pk,"
                " target_column, source_type, source_drive_id, source_file_name, source_tab,"
                " source_row, source_column, raw_value, ingested_value, ingested_at) VALUES %s",
                [(prov_offset + start + i + 1,
                  p["target_table"], p["target_pk"], p["target_column"],
                  p["source_type"], p["source_drive_id"], p["source_file_name"],
                  p["source_tab"], p["source_row"], p["source_column"],
                  p["raw_value"], p["ingested_value"], None)
                 for i, p in enumerate(chunk)],
                page_size=5000,
            )
        print(f"  data_provenance:    {len(all_prov)}  (IDs {prov_offset+1}–{prov_offset+len(all_prov)})")

        conn.commit()
        print("\nCommitted.")

    except Exception:
        conn.rollback()
        print("\nROLLBACK — error during write")
        raise
    finally:
        conn.close()

    # ── Post-write verification (from live Supabase) ──────────────────────────
    print("\n" + "=" * 70)
    print("POST-WRITE VERIFICATION (live Supabase)")
    print("=" * 70)

    INTENDED = {
        "unit": 4293, "lease": 4293, "tenant": 6090,
        "tenancy_record": 5569, "guarantor": 526,
        "parking_assignment": 3133, "storage_assignment": 1321,
        "unit_appliance": 2229,
    }

    vconn = get_conn()
    vcur = vconn.cursor()

    # 1. Row counts
    print("\n── 1. Row counts vs. dry-run targets ─────────────────────────────────")
    all_match = True
    for t, target in INTENDED.items():
        pk = {"unit": "unit_id", "tenant": "tenant_id", "lease": "lease_id",
              "tenancy_record": "tenancy_id", "guarantor": "guarantor_id",
              "parking_assignment": "parking_id", "storage_assignment": "storage_id",
              "unit_appliance": "unit_appliance_id"}[t]
        vcur.execute(f"SELECT COUNT(*) FROM {t}")
        actual = vcur.fetchone()[0]
        mark = "✓" if actual == target else "✗"
        print(f"  {mark} {t:<25}  actual={actual:>6}  target={target:>6}")
        if actual != target:
            all_match = False
    vcur.execute("SELECT COUNT(*) FROM data_provenance WHERE provenance_id > %s", (prov_offset,))
    prov_actual = vcur.fetchone()[0]
    mark = "✓" if prov_actual == len(all_prov) else "✗"
    print(f"  {mark} {'data_provenance (new)':<25}  actual={prov_actual:>6}  target={len(all_prov):>6}")
    if prov_actual != len(all_prov):
        all_match = False

    # 2. Orphaned FK check
    print("\n── 2. Orphaned FK check ──────────────────────────────────────────────")
    fk_checks = [
        ("unit.building_id", "SELECT COUNT(*) FROM unit u LEFT JOIN building b ON u.building_id=b.building_id WHERE b.building_id IS NULL"),
        ("lease.unit_id", "SELECT COUNT(*) FROM lease l LEFT JOIN unit u ON l.unit_id=u.unit_id WHERE u.unit_id IS NULL"),
        ("tenancy_record.tenant_id", "SELECT COUNT(*) FROM tenancy_record tr LEFT JOIN tenant t ON tr.tenant_id=t.tenant_id WHERE t.tenant_id IS NULL"),
        ("tenancy_record.lease_id", "SELECT COUNT(*) FROM tenancy_record tr LEFT JOIN lease l ON tr.lease_id=l.lease_id WHERE l.lease_id IS NULL"),
        ("guarantor.tenant_id", "SELECT COUNT(*) FROM guarantor g LEFT JOIN tenant t ON g.tenant_id=t.tenant_id WHERE t.tenant_id IS NULL"),
        ("guarantor.lease_id", "SELECT COUNT(*) FROM guarantor g LEFT JOIN lease l ON g.lease_id=l.lease_id WHERE l.lease_id IS NULL"),
        ("parking_assignment.lease_id", "SELECT COUNT(*) FROM parking_assignment pa LEFT JOIN lease l ON pa.lease_id=l.lease_id WHERE l.lease_id IS NULL"),
        ("storage_assignment.lease_id", "SELECT COUNT(*) FROM storage_assignment sa LEFT JOIN lease l ON sa.lease_id=l.lease_id WHERE l.lease_id IS NULL"),
        ("unit_appliance.lease_id", "SELECT COUNT(*) FROM unit_appliance ua LEFT JOIN lease l ON ua.lease_id=l.lease_id WHERE l.lease_id IS NULL"),
    ]
    for label, sql in fk_checks:
        vcur.execute(sql)
        n = vcur.fetchone()[0]
        mark = "✓" if n == 0 else "✗"
        print(f"  {mark} {label:<35}  orphans={n}")
        if n:
            all_match = False

    # 3. People-fix proof: Robichaud and Carbonneau from live DB
    print("\n── 3. People-fix proof (live DB) ─────────────────────────────────────")
    for search_name, label in [("Robichaud", "François Robichaud"), ("Carbonneau", "Tony Carbonneau")]:
        vcur.execute(
            "SELECT tenant_id, nom_complet FROM tenant WHERE nom_complet ILIKE %s",
            (f"%{search_name}%",),
        )
        matches = vcur.fetchall()
        print(f"\n  {label}: {len(matches)} tenant row(s) in DB")
        for tid, name in matches:
            print(f"    tenant_id={tid}  {name!r}")
            vcur.execute("SELECT tenancy_id, lease_id FROM tenancy_record WHERE tenant_id=%s", (tid,))
            for tenancy_id, lid in vcur.fetchall():
                print(f"      tenancy_record: tenancy_id={tenancy_id}  lease_id={lid}")
            vcur.execute("SELECT guarantor_id, lease_id FROM guarantor WHERE tenant_id=%s", (tid,))
            for gid, lid in vcur.fetchall():
                print(f"      guarantor:      guarantor_id={gid}  lease_id={lid}")

    # 4. VACANT units: unit + lease but zero tenancy_record
    print("\n── 4. VACANT units: unit+lease present, no tenancy_record ────────────")
    vcur.execute("""
        SELECT COUNT(DISTINCT l.lease_id)
        FROM lease l
        LEFT JOIN tenancy_record tr ON tr.lease_id = l.lease_id
        WHERE tr.tenancy_id IS NULL
    """)
    n_vacant_leases = vcur.fetchone()[0]
    # Confirm these units exist
    vcur.execute("""
        SELECT COUNT(DISTINCT l.unit_id)
        FROM lease l
        LEFT JOIN tenancy_record tr ON tr.lease_id = l.lease_id
        WHERE tr.tenancy_id IS NULL
    """)
    n_vacant_units = vcur.fetchone()[0]
    print(f"  Leases with no tenancy_record:  {n_vacant_leases}  (expected ≥51 — VACANT + commercial-only)")
    print(f"  Units behind those leases:      {n_vacant_units}")

    # 5. Provenance spot-check: 5 tenant rows
    print("\n── 5. Provenance spot-check (5 tenant rows) ──────────────────────────")
    vcur.execute("""
        SELECT dp.target_table, dp.target_pk, dp.target_column,
               dp.source_tab, dp.source_row, dp.source_column, dp.raw_value
        FROM data_provenance dp
        WHERE dp.target_table = 'tenant'
          AND dp.provenance_id > %s
        ORDER BY dp.target_pk, dp.provenance_id
        LIMIT 20
    """, (prov_offset,))
    rows = vcur.fetchall()
    seen_tids = []
    shown = 0
    for table, pk, col, tab, row, src_col, raw in rows:
        if pk not in seen_tids:
            seen_tids.append(pk)
            if len(seen_tids) > 5:
                break
            print(f"\n  tenant_id={pk}")
        if pk in seen_tids[:5]:
            print(f"    {col:<32}  tab={tab!r}  row={row}  col={src_col!r}  raw={str(raw)[:40]!r}")

    vconn.close()
    print()
    print("VERIFICATION COMPLETE" + (" — ALL CHECKS PASSED ✓" if all_match else " — SEE ✗ ABOVE"))
    print()


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    dry_run = "--write" not in sys.argv and not refresh
    run(dry_run=dry_run, refresh=refresh)
