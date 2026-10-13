"""
ingest_security.py — Dry-run (and eventual write) ingestion of:
  - entrance (one synthetic row per building)
  - building_camera_system
  - building_intercom
  - building_access_control
from File 8: Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx

Run:
    uv run python -m drive_pipeline.ingestion.ingest_security          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_security --write  # write
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.parse_calendar_requests import _match_building

_FILE8_PATH = ROOT / "work/dryrun_maintenance/Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx"
_SOURCE_FILE = "Cameras, Intercoms, Fobs, Garages - Internet Access.xlsx"
_SOMMAIRE_TAB = "Sommaire"

# Minimal overrides — only rows the fixed parser still can't resolve.
# Group A (STREET - CIV1,CIV2,CIV3), D (bureau qualifier), E (et compound) are
# now handled by the parser. These two remain:
#   Row 100: fuzzy matcher returns bldg 1 for 'Grande-Allée Ouest'+410 instead of bldg 101
#   Row 177: source typo — Sommaire says 480, DB has 470 (building_id=177); 480 not in TF
_ROW_OVERRIDES: dict[int, int] = {
    100: 101,  # 'Grande-Allée Ouest 410-420 (CHDM)' — fuzzy mismatch to bldg 1
    177: 177,  # 'Yves-Carbonneau 480' — confirmed typo for 470 (bldg_id=177) per François 2026-10-02
}

# Sensitive columns — value written to DB as-is, but provenance gets [REDACTED-SENSITIVE]
# and dry-run output shows [populated]/[null]
_SENSITIVE: dict[str, set[str]] = {
    "building_camera_system":  {"password"},
    "building_intercom":       {"keyless_code_general", "keyless_code_maintenance", "keyless_code_tenant"},
    "building_access_control": {"ip_module_password", "system_login", "system_password"},
}

# camera_platform enum values
_PLATFORM_MAP: dict[str, str] = {
    "ivms-4500":       "hik_connect",
    "ivms-4501":       "hik_connect",
    "ivms-4502":       "hik_connect",
    "cloud":           "cloud_generic",
    "cloud\nivms-4500": "hik_connect",
    "cloud/ivms-4500": "hik_connect",
    "ubox":            "ubox",
    "blink":           "blink",
}

# access_status_enum for camera installed field
def _map_installed(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("no", "n/a"):
        return "Non"
    if s == "installation prévue":
        return "Installation_prevue"
    if s == "yes":
        return "Oui"
    return None

def _map_platform(raw: str | None) -> str | None:
    if raw is None:
        return None
    return _PLATFORM_MAP.get(str(raw).strip().lower())

def _is_yes(val) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s.startswith("yes") or s.startswith("oui") or s == "ligne dure"

def _nonempty(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s not in ("-", "n/a", "none", "#ref!") else None

# ── Address parsing ────────────────────────────────────────────────────────────

_CIVIC_SPLIT_RE = re.compile(r"^(\d[\d-]*)\s+(.+)$")
_RANGE_STRIP_RE = re.compile(r"\s*(?:/\s*)?(?:[\d-]+\s*,\s*)+[\d-]+\s*$")
_TO_STRIP_RE    = re.compile(r"\s+(?:à|a)\s+\d[\d-]*", re.I)
_PARENS_RE      = re.compile(r"\s*\(.*?\)")
# "STREET - CIV1, CIV2, CIV3" — captures first civic from comma-separated list
_DASH_CIVICS_RE = re.compile(r"^(.+?)\s*[-]\s*(\d[\d-]*)(?:\s*,\s*\d[\d-]*)+\s*$")
# "bureau 201", "apt 4B" etc. — suite qualifiers that mask the real civic
_BUREAU_RE      = re.compile(r"\s+(?:bureau|apt|suite|local)\s+\S+", re.I)
# French geographic prefix: "Côte D'Abraham" → "Abraham"
_GEO_PREFIX_RE  = re.compile(r"^(?:c[oô]te|chemin|route)\s+(?:d[e']?\s*)?", re.I)


def _split_building_adresse(adresse: str) -> tuple[str | None, str]:
    """Split building.adresse → (civic_number, street) for entrance rows."""
    m = _CIVIC_SPLIT_RE.match(adresse.strip())
    if m:
        return m.group(1), m.group(2)
    return None, adresse


def _parse_sommaire_addr(raw: str) -> tuple[str, str | None]:
    """Extract (street, first_civic) from a raw Sommaire address cell."""
    s = _PARENS_RE.sub("", raw).strip()
    s = _BUREAU_RE.sub("", s)                        # strip "bureau 201" etc.
    # Split compound "STREET1 - CIV1 et STREET2 CIV2" — take first component
    s = re.split(r"\s+et\s+", s, maxsplit=1, flags=re.I)[0].strip()
    s = _TO_STRIP_RE.sub("", s)                      # strip "à/a NNN" range suffix

    # "STREET - CIV1, CIV2, CIV3" → take first civic
    m = _DASH_CIVICS_RE.match(s)
    if m:
        return m.group(1).strip(), m.group(2).split("-")[0]

    # Fall back to RANGE_STRIP then standard patterns
    s = _RANGE_STRIP_RE.sub("", s).strip().rstrip(",").strip()

    m = re.match(r"^(\d[\d-]*)\s+(.+)$", s)
    if m:
        return m.group(2).strip(), m.group(1).split("-")[0]

    m = re.match(r"^(.+?)[\s,/-]+(\d[\d-]*)$", s)
    if m:
        street = m.group(1).strip().rstrip("-").strip()
        civic  = m.group(2).split("-")[0]
        return street, civic

    return s, None


# ── Building address lookup ────────────────────────────────────────────────────

def _lookup_bid(raw_addr: str, bldg_by_addr: dict[str, int]) -> int | None:
    street, civic = _parse_sommaire_addr(raw_addr)
    result = _match_building(street, civic, None)
    if result:
        return bldg_by_addr.get(result.get("unique_building_name"))
    # Fallback 1: strip French prepositions ("de la", "du", "l'", …)
    m = re.match(r"^(?:de la |de l'|du |des |de |la |le |les |l')(.+)$", street, re.I)
    if m:
        result = _match_building(m.group(1).strip(), civic, None)
        if result:
            return bldg_by_addr.get(result.get("unique_building_name"))
    # Fallback 2: strip geographic prefix ("Côte D'Abraham" → "Abraham")
    gm = _GEO_PREFIX_RE.match(street)
    if gm:
        result = _match_building(street[gm.end():].strip("' "), civic, None)
        if result:
            return bldg_by_addr.get(result.get("unique_building_name"))
    return None


# ── Panel S/N or IP helper ────────────────────────────────────────────────────

def _panel_sn_or_ip(sn_raw, ip_raw) -> str | None:
    sn = _nonempty(sn_raw)
    ip = _nonempty(ip_raw)
    return sn or ip


# ── Provenance helpers ────────────────────────────────────────────────────────

def _prov_val(table: str, col: str, val: str | None) -> str | None:
    if col in _SENSITIVE.get(table, set()):
        return "[REDACTED-SENSITIVE]"
    return val


def _fmt_cred(table: str, col: str, val) -> str:
    if col in _SENSITIVE.get(table, set()):
        return "[populated]" if val is not None else "[null]"
    return repr(val)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    # ── DB lookups ────────────────────────────────────────────────────────────
    cur.execute("SELECT adresse, building_id FROM building")
    bldg_by_addr = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT building_id, adresse, ville, code_postal FROM building ORDER BY building_id")
    all_buildings = cur.fetchall()  # (building_id, adresse, ville, code_postal)

    cur.execute("SELECT COALESCE(MAX(entrance_id),      0) FROM entrance")
    next_entrance_id = cur.fetchone()[0] + 1
    cur.execute("SELECT COALESCE(MAX(camera_system_id), 0) FROM building_camera_system")
    next_camera_id   = cur.fetchone()[0] + 1
    cur.execute("SELECT COALESCE(MAX(intercom_id),      0) FROM building_intercom")
    next_intercom_id = cur.fetchone()[0] + 1
    cur.execute("SELECT COALESCE(MAX(access_control_id),0) FROM building_access_control")
    next_ac_id       = cur.fetchone()[0] + 1
    cur.execute("SELECT COALESCE(MAX(provenance_id),    0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]

    # ── Read Sommaire ─────────────────────────────────────────────────────────
    wb = openpyxl.load_workbook(str(_FILE8_PATH), read_only=True, data_only=True)
    ws = wb[_SOMMAIRE_TAB]
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    data_rows = all_rows[1:]  # skip header row

    # ── Match each Sommaire row → building_id ─────────────────────────────────
    # For each building_id we may have at most one Sommaire row
    # (if multiple Sommaire rows hit the same bid, they each get their own security records)
    sommaire_records: list[dict] = []
    unmatched: list[tuple[int, str]] = []
    unresolved: list[tuple[int, str]] = []

    for row_idx, row in enumerate(data_rows):
        raw_addr = row[1]
        if raw_addr is None:
            continue
        addr_s = str(raw_addr).strip()
        if not addr_s:
            continue
        # Skip the non-building last row
        if "caméra bink" in addr_s.lower() or "camera bink" in addr_s.lower():
            continue

        excel_row_num = row_idx + 2

        # Hardcoded overrides take precedence over auto-matching
        if excel_row_num in _ROW_OVERRIDES:
            bid = _ROW_OVERRIDES[excel_row_num]
        else:
            bid = _lookup_bid(addr_s, bldg_by_addr)

        if bid is None:
            # Check for Yves-Carbonneau 480 (known typo in source)
            if "carbonneau" in addr_s.lower() and "480" in addr_s:
                unresolved.append((excel_row_num, addr_s))
                continue
            unmatched.append((excel_row_num, addr_s))
            continue

        rec = {"bid": bid, "excel_row": excel_row_num, "raw_addr": addr_s}

        # Camera fields
        rec["cam_installed"]  = _nonempty(row[6])
        rec["cam_remote"]     = _nonempty(row[7])
        rec["cam_functional"] = _nonempty(row[8])
        rec["cam_ip_domain"]  = _nonempty(row[10])
        rec["cam_port"]       = _nonempty(row[11])
        rec["cam_platform"]   = _nonempty(row[12])
        rec["cam_username"]   = _nonempty(row[13])
        rec["cam_password"]   = _nonempty(row[14])

        # Intercom fields
        rec["intercom_present"] = _is_yes(row[17])
        rec["intercom_raw_col17"] = _nonempty(row[17])
        rec["intercom_brand"]   = _nonempty(row[18])
        rec["intercom_keyless_general"]     = _nonempty(row[21])
        rec["intercom_keyless_maintenance"] = _nonempty(row[22])
        rec["intercom_keyless_tenant"]      = _nonempty(row[23])
        rec["intercom_dyndns"]   = _nonempty(row[25])
        rec["intercom_panel"]    = _nonempty(row[26])

        # Access control fields
        rec["ac_present"] = _is_yes(row[29])
        rec["ac_brand"]   = _nonempty(row[30])
        # Paradox only (cols 45-51)
        rec["ac_panel_type"]   = _nonempty(row[45]) if len(row) > 45 else None
        rec["ac_conn_opt"]     = _nonempty(row[46]) if len(row) > 46 else None
        rec["ac_sn_raw"]       = row[47] if len(row) > 47 else None
        rec["ac_ip_raw"]       = row[48] if len(row) > 48 else None
        rec["ac_ip_mod_pw"]    = _nonempty(row[49]) if len(row) > 49 else None
        rec["ac_sys_login"]    = _nonempty(row[50]) if len(row) > 50 else None
        rec["ac_sys_pw"]       = _nonempty(str(row[51])) if len(row) > 51 and row[51] is not None else None

        sommaire_records.append(rec)

    # ── Derive access_method per building_id ──────────────────────────────────
    # First Sommaire match wins
    am_by_bid: dict[int, str | None] = {}
    for rec in sommaire_records:
        bid = rec["bid"]
        if bid in am_by_bid:
            continue
        if rec["intercom_present"]:
            am_by_bid[bid] = "intercom_release"
        elif rec["ac_present"]:
            am_by_bid[bid] = "fob"
        else:
            am_by_bid[bid] = None

    # ── Build entrance rows (one per DB building) ─────────────────────────────
    entrance_rows: list[dict] = []
    for building_id, adresse, ville, code_postal in all_buildings:
        civic, street = _split_building_adresse(adresse)
        entrance_rows.append({
            "entrance_id":  next_entrance_id + len(entrance_rows),
            "building_id":  building_id,
            "civic_number": civic,
            "street":       street,
            "postal_code":  code_postal,
            "access_method": am_by_bid.get(building_id),  # None if not in File 8
        })

    # entrance_id lookup: building_id → entrance_id (first entrance per building)
    entrance_by_bid: dict[int, int] = {}
    for e in entrance_rows:
        entrance_by_bid.setdefault(e["building_id"], e["entrance_id"])

    # ── Build camera rows ─────────────────────────────────────────────────────
    camera_rows: list[dict] = []
    for i, rec in enumerate(sommaire_records):
        # Include if there's any camera field data at all
        has_cam_data = any(rec[k] is not None for k in (
            "cam_installed", "cam_remote", "cam_functional",
            "cam_ip_domain", "cam_port", "cam_platform", "cam_username", "cam_password"
        ))
        if not has_cam_data:
            continue
        camera_rows.append({
            "camera_system_id": next_camera_id + len(camera_rows),
            "building_id":      rec["bid"],
            "installed":        _map_installed(rec["cam_installed"]),
            "accessible_remote": rec["cam_remote"],
            "functional":       rec["cam_functional"],
            "platform":         _map_platform(rec["cam_platform"]),
            "ip_domain":        rec["cam_ip_domain"],
            "port":             str(rec["cam_port"]) if rec["cam_port"] else None,
            "username":         rec["cam_username"],
            "password":         rec["cam_password"],
            "_excel_row":       rec["excel_row"],
            "_raw_installed":   rec["cam_installed"],
            "_raw_platform":    rec["cam_platform"],
        })

    # ── Build intercom rows ───────────────────────────────────────────────────
    intercom_rows: list[dict] = []
    intercom_no_entrance: list[int] = []
    for rec in sommaire_records:
        if not rec["intercom_present"]:
            continue
        eid = entrance_by_bid.get(rec["bid"])
        if eid is None:
            intercom_no_entrance.append(rec["bid"])
            continue
        intercom_rows.append({
            "intercom_id":            next_intercom_id + len(intercom_rows),
            "entrance_id":            eid,
            "brand":                  rec["intercom_brand"],
            "dyndns_address":         rec["intercom_dyndns"],
            "panel_model":            rec["intercom_panel"],
            "is_master_building":     None,  # no source column for this
            "keyless_code_general":   rec["intercom_keyless_general"],
            "keyless_code_maintenance": rec["intercom_keyless_maintenance"],
            "keyless_code_tenant":    rec["intercom_keyless_tenant"],
            "_building_id":           rec["bid"],
            "_excel_row":             rec["excel_row"],
        })

    # ── Build access control rows ─────────────────────────────────────────────
    ac_rows: list[dict] = []
    for rec in sommaire_records:
        if not rec["ac_present"]:
            continue
        brand = rec["ac_brand"]
        # Skip N/A brand (shouldn't have ac_present=True, but guard anyway)
        if brand is None:
            brand = None  # still create row; brand column is nullable
        panel_sn_or_ip = _panel_sn_or_ip(rec["ac_sn_raw"], rec["ac_ip_raw"])
        ac_rows.append({
            "access_control_id": next_ac_id + len(ac_rows),
            "building_id":       rec["bid"],
            "brand":             brand,
            "panel_type":        rec["ac_panel_type"],
            "connection_option": rec["ac_conn_opt"],
            "panel_serial_or_ip": panel_sn_or_ip,
            "ip_module_password": rec["ac_ip_mod_pw"],
            "system_login":      rec["ac_sys_login"],
            "system_password":   rec["ac_sys_pw"],
            "_excel_row":        rec["excel_row"],
        })

    # ── Dry-run report ────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("SECURITY INGEST DRY RUN")
    print("="*70)

    print(f"\n── Building match coverage (Sommaire) ──────────────────────────────")
    total_data_rows = len(sommaire_records) + len(unmatched) + len(unresolved)
    print(f"  Total Sommaire data rows:   {total_data_rows}")
    print(f"  Auto-matched:               {len(sommaire_records)}")
    print(f"  UNMATCHED (no building_id): {len(unmatched)}")
    for er, addr in unmatched:
        print(f"    Row {er}: {addr!r}")
    print(f"  UNRESOLVED (source error):  {len(unresolved)}")
    for er, addr in unresolved:
        print(f"    Row {er}: {addr!r}  ← Yves-Carbonneau 480; DB has 470")

    print(f"\n── Row counts ──────────────────────────────────────────────────────")
    print(f"  entrance           : {len(entrance_rows):>4}  (one per DB building)")
    print(f"  building_camera_system: {len(camera_rows):>4}  (Sommaire rows with cam data)")
    print(f"  building_intercom  : {len(intercom_rows):>4}  (Sommaire rows where intercom=Yes)")
    print(f"  building_access_control: {len(ac_rows):>4}  (Sommaire rows where access control=Yes)")

    print(f"\n── Entrance field coverage ─────────────────────────────────────────")
    _cnt = lambda rows, f: sum(1 for r in rows if r.get(f) is not None)
    print(f"  civic_number populated:  {_cnt(entrance_rows, 'civic_number')}/{len(entrance_rows)}")
    print(f"  street populated:        {_cnt(entrance_rows, 'street')}/{len(entrance_rows)}")
    print(f"  postal_code populated:   {_cnt(entrance_rows, 'postal_code')}/{len(entrance_rows)}")
    am_counts = {}
    for e in entrance_rows:
        am = e["access_method"]
        am_counts[am] = am_counts.get(am, 0) + 1
    for am, cnt in sorted(am_counts.items(), key=lambda x: str(x[0])):
        print(f"  access_method={am!r}: {cnt}")

    print(f"\n── Camera field coverage ({len(camera_rows)} rows) ────────────────────────────")
    cam_fields = ["installed", "accessible_remote", "functional", "platform",
                  "ip_domain", "port", "username", "password"]
    for f in cam_fields:
        cnt = sum(1 for r in camera_rows if r.get(f) is not None)
        if f in _SENSITIVE["building_camera_system"]:
            print(f"  {f:<22}: {cnt:>3}/{len(camera_rows)} (credential — [populated]/[null] only)")
        else:
            print(f"  {f:<22}: {cnt:>3}/{len(camera_rows)}")

    installed_dist = {}
    for r in camera_rows:
        k = r.get("_raw_installed")
        installed_dist[k] = installed_dist.get(k, 0) + 1
    print(f"  installed raw→enum: ", end="")
    for raw, cnt in sorted(installed_dist.items(), key=lambda x: str(x[0])):
        mapped = _map_installed(raw)
        print(f"'{raw}'→{mapped!r}({cnt})", end="  ")
    print()
    platform_dist = {}
    for r in camera_rows:
        k = r.get("_raw_platform")
        mapped = _map_platform(k)
        platform_dist[(k, mapped)] = platform_dist.get((k, mapped), 0) + 1
    print(f"  platform raw→enum:")
    for (raw, mapped), cnt in sorted(platform_dist.items(), key=lambda x: str(x[0])):
        print(f"    {raw!r} → {mapped!r} ({cnt} rows)")

    print(f"\n── Intercom field coverage ({len(intercom_rows)} rows) ──────────────────────────")
    intercom_fields = ["brand", "dyndns_address", "panel_model", "is_master_building",
                       "keyless_code_general", "keyless_code_maintenance", "keyless_code_tenant"]
    for f in intercom_fields:
        cnt = sum(1 for r in intercom_rows if r.get(f) is not None)
        db_f = f  # column name in row dict
        if f in _SENSITIVE["building_intercom"]:
            print(f"  {f:<28}: {cnt:>3}/{len(intercom_rows)} (credential — [populated]/[null] only)")
        else:
            print(f"  {f:<28}: {cnt:>3}/{len(intercom_rows)}")
    if intercom_no_entrance:
        print(f"  WARNING: {len(intercom_no_entrance)} intercom rows skipped (entrance not found for building_ids: {intercom_no_entrance})")

    print(f"\n── Access control field coverage ({len(ac_rows)} rows) ────────────────────────")
    ac_fields = ["brand", "panel_type", "connection_option", "panel_serial_or_ip",
                 "ip_module_password", "system_login", "system_password"]
    for f in ac_fields:
        cnt = sum(1 for r in ac_rows if r.get(f) is not None)
        if f in _SENSITIVE["building_access_control"]:
            print(f"  {f:<24}: {cnt:>3}/{len(ac_rows)} (credential — [populated]/[null] only)")
        else:
            print(f"  {f:<24}: {cnt:>3}/{len(ac_rows)}")
    ac_brand_dist = {}
    for r in ac_rows:
        k = r.get("brand")
        ac_brand_dist[k] = ac_brand_dist.get(k, 0) + 1
    print(f"  brand distribution: {dict(sorted(ac_brand_dist.items(), key=lambda x: str(x[0])))}")

    print(f"\n── Leftover File 8 columns (not mapped to any schema field) ────────")
    print("  Sommaire:")
    print("    [2]  Internet Service Provider")
    print("    [3]  Internet broadcasting provider (Wi-Fi antenna manager)")
    print("    [4]  Technical Support Provider")
    print("    [5]  Telephone Provider")
    print("    [9]  CAMERAS: Location Map")
    print("    [15] CAMERAS: Internet Explorer (browser access)")
    print("    [16] CAMERAS: Notes")
    print("    [19] INTERCOM: Communication Mode for Unlock")
    print("    [20] INTERCOM: Remote Access")
    print("    [24] INTERCOM: Programming Procedure (link)")
    print("    [27] INTERCOM: PC Connection")
    print("    [28] INTERCOM: Notes")
    print("    [31] ACCESS CONTROL: Remote Access")
    print("    [32] ACCESS CONTROL: Controlled Doors")
    print("    [33] ACCESS CONTROL: Notes")
    print("    [34] IMPORTANT NOTE (tenant welcome message)")
    print("    [35] ACCESS CONTROL: Keyless Code (maintenance) [dup of 22?]")
    print("    [36] ACCESS CONTROL: Keyless Code (tenant) LIKELY TO DELETE")
    print("    [37] ACCESS CONTROL: Keyless Code (tenant pool) LIKELY TO DELETE")
    print("    [38] ACCESS CONTROL: Programming Procedure (link)")
    print("    [39-44] ACCESS CONTROL: AKUVOX ONLY (all N/A in current data)")
    print("    [52] ACCESS CONTROL: PARADOX ONLY DYNDNS address")
    print("  Puces sheet: supplementary Paradox panel detail sheet")
    print("    — same data as Sommaire cols 45-52; no additional fields to map")
    print("    — col [8] DYNDNS, col [9] Notes: not in schema")
    print("  Caméra sheet: supplementary camera detail sheet (not fully parsed)")
    print("  Intercom sheet: contains #REF! errors; Sommaire data preferred")
    print("  Other sheets: Instructions (read-only), Template, Contact, Données")

    print(f"\n── Ambiguous / flagged rows ────────────────────────────────────────")
    # Platform ambiguities (compound values)
    compound = [(r["_excel_row"], r["_raw_platform"])
                for r in camera_rows if r["_raw_platform"] and "/" in str(r["_raw_platform"])]
    compound += [(r["_excel_row"], r["_raw_platform"])
                 for r in camera_rows if r["_raw_platform"] and "\n" in str(r["_raw_platform"])]
    if compound:
        print(f"  Camera platform compound values (mapped to hik_connect):")
        for er, p in compound:
            print(f"    Row {er}: {p!r}")

    # Duplicate building_id in camera or AC (multiple Sommaire rows → same building)
    cam_bid_counts: dict[int, int] = {}
    for r in camera_rows:
        bid = r["building_id"]
        cam_bid_counts[bid] = cam_bid_counts.get(bid, 0) + 1
    dup_cam = {bid: cnt for bid, cnt in cam_bid_counts.items() if cnt > 1}
    if dup_cam:
        print(f"  Buildings with multiple camera rows: {dup_cam}")

    ac_bid_counts: dict[int, int] = {}
    for r in ac_rows:
        bid = r["building_id"]
        ac_bid_counts[bid] = ac_bid_counts.get(bid, 0) + 1
    dup_ac = {bid: cnt for bid, cnt in ac_bid_counts.items() if cnt > 1}
    if dup_ac:
        print(f"  Buildings with multiple access_control rows: {dup_ac}")

    # Akuvox AC rows — Sommaire cols 45-51 may be N/A (expected)
    akuvox_ac = [r for r in ac_rows if r.get("brand") and "akuvox" in str(r["brand"]).lower()]
    if akuvox_ac:
        ak_no_panel = [r for r in akuvox_ac if r["panel_type"] in (None, "N/A") or
                       (r["panel_type"] and "n/a" in str(r["panel_type"]).lower())]
        print(f"  Akuvox AC rows: {len(akuvox_ac)} total, {len(ak_no_panel)} with panel_type=N/A (PARADOX cols don't apply)")

    # AC rows where brand = Salto (no schema support for Salto-specific fields)
    salto = [r for r in ac_rows if r.get("brand") and "salto" in str(r["brand"]).lower()]
    if salto:
        print(f"  Salto AC rows: {len(salto)} (brand stored, no Salto-specific credential columns available)")

    print(f"\n{'='*70}")
    if dry_run:
        print(f"DRY RUN COMPLETE — no data written.")
        print(f"To write: uv run python -m drive_pipeline.ingestion.ingest_security --write")
        conn.close()
        return

    # ── WRITE ──────────────────────────────────────────────────────────────────
    print(f"\nWriting to database…")
    try:
        # 1. entrance
        execute_values(
            cur,
            """INSERT INTO entrance
               (entrance_id, building_id, civic_number, street, postal_code, access_method)
               VALUES %s""",
            [(e["entrance_id"], e["building_id"], e["civic_number"],
              e["street"], e["postal_code"], e["access_method"])
             for e in entrance_rows],
            page_size=500,
        )
        print(f"  Inserted {len(entrance_rows)} entrance rows.")

        # 2. building_camera_system
        if camera_rows:
            execute_values(
                cur,
                """INSERT INTO building_camera_system
                   (camera_system_id, building_id, installed, accessible_remote,
                    functional, platform, ip_domain, port, username, password)
                   VALUES %s""",
                [(r["camera_system_id"], r["building_id"], r["installed"],
                  r["accessible_remote"], r["functional"], r["platform"],
                  r["ip_domain"], r["port"], r["username"], r["password"])
                 for r in camera_rows],
                page_size=500,
            )
            print(f"  Inserted {len(camera_rows)} building_camera_system rows.")

        # 3. building_intercom
        if intercom_rows:
            execute_values(
                cur,
                """INSERT INTO building_intercom
                   (intercom_id, entrance_id, brand, dyndns_address, panel_model,
                    is_master_building, keyless_code_general,
                    keyless_code_maintenance, keyless_code_tenant)
                   VALUES %s""",
                [(r["intercom_id"], r["entrance_id"], r["brand"],
                  r["dyndns_address"], r["panel_model"], r["is_master_building"],
                  r["keyless_code_general"], r["keyless_code_maintenance"],
                  r["keyless_code_tenant"])
                 for r in intercom_rows],
                page_size=500,
            )
            print(f"  Inserted {len(intercom_rows)} building_intercom rows.")

        # 4. building_access_control
        if ac_rows:
            execute_values(
                cur,
                """INSERT INTO building_access_control
                   (access_control_id, building_id, brand, panel_type,
                    connection_option, panel_serial_or_ip,
                    ip_module_password, system_login, system_password)
                   VALUES %s""",
                [(r["access_control_id"], r["building_id"], r["brand"],
                  r["panel_type"], r["connection_option"], r["panel_serial_or_ip"],
                  r["ip_module_password"], r["system_login"], r["system_password"])
                 for r in ac_rows],
                page_size=500,
            )
            print(f"  Inserted {len(ac_rows)} building_access_control rows.")

        # 5. data_provenance
        prov: list[tuple] = []
        pnum = prov_offset

        def _add_prov(table, pk, col, src_row, raw_val, ingested_val):
            nonlocal pnum
            pnum += 1
            r_val = _prov_val(table, col, str(raw_val) if raw_val is not None else None)
            i_val = _prov_val(table, col, str(ingested_val) if ingested_val is not None else None)
            prov.append((pnum, table, pk, col, "spreadsheet", None,
                         _SOURCE_FILE, _SOMMAIRE_TAB, src_row, col,
                         r_val, i_val, None))

        def _add_synth_prov(table, pk, col, raw_val, ingested_val):
            nonlocal pnum
            pnum += 1
            prov.append((pnum, table, pk, col, "synthetic_from_building", None,
                         None, None, None, None,
                         str(raw_val) if raw_val is not None else None,
                         str(ingested_val) if ingested_val is not None else None,
                         None))

        for e in entrance_rows:
            eid = e["entrance_id"]
            for col, val in [("civic_number", e["civic_number"]),
                             ("street", e["street"]),
                             ("postal_code", e["postal_code"])]:
                _add_synth_prov("entrance", eid, col, val, val)
            if e["access_method"] is not None:
                _add_prov("entrance", eid, "access_method",
                          None, e["access_method"], e["access_method"])

        for r in camera_rows:
            cid = r["camera_system_id"]
            er = r["_excel_row"]
            for col, raw, ing in [
                ("installed",        r["_raw_installed"], r["installed"]),
                ("accessible_remote", r["accessible_remote"], r["accessible_remote"]),
                ("functional",       r["functional"],     r["functional"]),
                ("platform",         r["_raw_platform"],  r["platform"]),
                ("ip_domain",        r["ip_domain"],      r["ip_domain"]),
                ("port",             r["port"],           r["port"]),
                ("username",         r["username"],       r["username"]),
                ("password",         r["password"],       r["password"]),
            ]:
                if raw is not None or ing is not None:
                    _add_prov("building_camera_system", cid, col, er, raw, ing)

        for r in intercom_rows:
            iid = r["intercom_id"]
            er = r["_excel_row"]
            for col, val in [
                ("brand",                    r["brand"]),
                ("dyndns_address",           r["dyndns_address"]),
                ("panel_model",              r["panel_model"]),
                ("keyless_code_general",     r["keyless_code_general"]),
                ("keyless_code_maintenance", r["keyless_code_maintenance"]),
                ("keyless_code_tenant",      r["keyless_code_tenant"]),
            ]:
                if val is not None:
                    _add_prov("building_intercom", iid, col, er, val, val)

        for r in ac_rows:
            aid = r["access_control_id"]
            er = r["_excel_row"]
            sn_or_ip = r["panel_serial_or_ip"]
            for col, raw, ing in [
                ("brand",             r["brand"],             r["brand"]),
                ("panel_type",        r["panel_type"],        r["panel_type"]),
                ("connection_option", r["connection_option"], r["connection_option"]),
                ("panel_serial_or_ip", sn_or_ip,             sn_or_ip),
                ("ip_module_password", r["ip_module_password"], r["ip_module_password"]),
                ("system_login",      r["system_login"],      r["system_login"]),
                ("system_password",   r["system_password"],   r["system_password"]),
            ]:
                if raw is not None or ing is not None:
                    _add_prov("building_access_control", aid, col, er, raw, ing)

        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov,
            page_size=5000,
        )
        print(f"  Inserted {len(prov)} data_provenance rows.")

        conn.commit()
        print(f"\nCommitted successfully.")

        for tbl in ("entrance", "building_camera_system", "building_intercom",
                    "building_access_control", "data_provenance"):
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            print(f"  {tbl} total: {cur.fetchone()[0]}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
