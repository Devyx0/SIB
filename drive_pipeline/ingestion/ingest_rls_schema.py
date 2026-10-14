"""
DO NOT RE-RUN. All schema changes go through supabase/migrations/ (supabase db diff → new migration file).

ingest_rls_schema.py — RLS schema migrations: new tables, credential migration, views.

Creates:
  - employee_role (junction)
  - employee_building_assignment (A5 dedications: JFME/SAHA/MACH)
  - building_security_credential (migrated from camera_system + access_control)
  - Views: lease_field_view, maintenance_request_tech_view,
           parking_assignment_field_view, storage_assignment_field_view

Run:
    uv run python -m drive_pipeline.ingestion.ingest_rls_schema                    # dry run
    uv run python -m drive_pipeline.ingestion.ingest_rls_schema --write            # tables, migrate, A5, views — NO DROP
    uv run python -m drive_pipeline.ingestion.ingest_rls_schema --write --drop     # DROP 4 credential columns (irreversible)

Apply --drop only after verifying building_security_credential has 79 rows.
"""
from __future__ import annotations

import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from psycopg2.extras import execute_values
from drive_pipeline.ingestion.db import get_conn

_SOURCE_FILE = "rls-proposal-v2.md"


def _drop_credential_columns() -> None:
    """Irreversible: DROP the 4 credential columns from their original tables.
    Run only after verifying building_security_credential has all expected rows."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM building_security_credential")
        n = cur.fetchone()[0]
        if n == 0:
            print("ERROR: building_security_credential is empty — run --write first.")
            return
        print(f"building_security_credential has {n} rows. Dropping credential columns…")
        cur.execute("ALTER TABLE building_camera_system DROP COLUMN IF EXISTS password")
        cur.execute("ALTER TABLE building_access_control DROP COLUMN IF EXISTS ip_module_password")
        cur.execute("ALTER TABLE building_access_control DROP COLUMN IF EXISTS system_login")
        cur.execute("ALTER TABLE building_access_control DROP COLUMN IF EXISTS system_password")
        conn.commit()
        print("Dropped: building_camera_system.password, building_access_control.ip_module_password/system_login/system_password")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

_TABLE_DDL = [
    """CREATE TABLE IF NOT EXISTS employee_role (
        employee_role_id serial PRIMARY KEY,
        employee_id integer NOT NULL REFERENCES employee(employee_id) ON DELETE CASCADE,
        role varchar NOT NULL CHECK (role IN ('admin','director','coordinator','technician','contractor')),
        UNIQUE(employee_id, role)
    )""",
    """CREATE TABLE IF NOT EXISTS employee_building_assignment (
        assignment_id serial PRIMARY KEY,
        employee_id integer NOT NULL REFERENCES employee(employee_id) ON DELETE CASCADE,
        building_id integer NOT NULL REFERENCES building(building_id) ON DELETE CASCADE,
        assignment_type varchar NOT NULL,
        notes text,
        UNIQUE(employee_id, building_id)
    )""",
    """CREATE TABLE IF NOT EXISTS building_security_credential (
        credential_id serial PRIMARY KEY,
        building_id integer NOT NULL UNIQUE REFERENCES building(building_id) ON DELETE CASCADE,
        camera_password varchar,
        access_ip_module_password varchar,
        access_system_login varchar,
        access_system_password varchar
    )""",
]

_VIEW_DDL = [
    ("lease_field_view", """CREATE OR REPLACE VIEW lease_field_view
       WITH (security_invoker = true) AS
       SELECT unit_id, debut_bail, fin_bail, langue_bail, statut FROM lease"""),
    ("maintenance_request_tech_view", """CREATE OR REPLACE VIEW maintenance_request_tech_view
       WITH (security_invoker = true) AS
       SELECT
           request_id, building_id, unit_id, project_id, source_calendar,
           sector_id, equipment_id,
           banked_queue_date, delegable_notes, report_notes,
           duplicate_of_request_id, synergy_request_ids, synergy_reason,
           unit_label, project_label, time_estimate_bucket, time_estimate_raw,
           vendor_id, subcontractor_name, tenant_agreement_notes, other_notes,
           caller_tenant_id, caller_name, caller_phone, dispatched, work_performed,
           tenant_present, follow_up_expected, event_id, html_link, start_date,
           raw_title, body_format, parse_status, source_calendar_id,
           assigned_employee_code_raw, urgency_raw, civic, street_raw,
           problem_summary, problems, entry_permission, animals, occupants_raw,
           bail_raw, ft_link, ft_name, historique_raw, tri_raw, delegable_raw,
           report_raw, doublons, synergie_raw, complexite_raw, embourbement_raw,
           gravity_raw, signed_date, submission_date, caller_type, caller_email,
           fees_advised, category_raw, address_urgency, assigned_employee_id
       FROM maintenance_request"""),
    # EXCLUDED from maintenance_request_tech_view (7 routing/triage columns):
    # urgency_tier, complexity_tier, congestion_level, delegable_status,
    # report_status, triage_summary, proposed_assignee
    # NOTE: delegable_notes and report_notes ARE included — they are field notes
    # written by the technician, not internal routing decisions.
    ("parking_assignment_field_view", """CREATE OR REPLACE VIEW parking_assignment_field_view
       WITH (security_invoker = true) AS
       SELECT parking_id, lease_id, mode, location_type, count FROM parking_assignment"""),
    ("storage_assignment_field_view", """CREATE OR REPLACE VIEW storage_assignment_field_view
       WITH (security_invoker = true) AS
       SELECT storage_id, lease_id, mode, count FROM storage_assignment"""),
]

# SAHA building_ids 33-40 (Chamonix + Sully); MACH is queried at runtime
_STATIC_A5 = [
    ("JFME", [150],                 "a5_dedicated", "350 Ch Ste-Foy; lives on site"),
    ("SAHA", list(range(33, 41)),   "a5_dedicated", "Chamonix + Sully complexes"),
]


def run(dry_run: bool = True, drop_credentials: bool = False) -> None:
    if drop_credentials and not dry_run:
        _drop_credential_columns()
        return
    conn = get_conn()
    cur = conn.cursor()

    # ── Gather preview data ────────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT COALESCE(bcs.building_id, bac.building_id)
            FROM building_camera_system bcs
            FULL OUTER JOIN building_access_control bac ON bcs.building_id = bac.building_id
            WHERE bcs.password IS NOT NULL
               OR bac.ip_module_password IS NOT NULL
               OR bac.system_login IS NOT NULL
               OR bac.system_password IS NOT NULL
        ) sub
    """)
    cred_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM building_camera_system WHERE password IS NOT NULL")
    cam_with_pw = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM building_access_control
                   WHERE ip_module_password IS NOT NULL OR system_login IS NOT NULL OR system_password IS NOT NULL""")
    ac_with_creds = cur.fetchone()[0]

    cur.execute("SELECT building_id FROM building WHERE sector_id IN (2,3) ORDER BY building_id")
    levis_bids = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT COUNT(*) FROM data_provenance WHERE target_table='building_camera_system' AND target_column='password'")
    prov_cam = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM data_provenance
                   WHERE target_table='building_access_control'
                     AND target_column IN ('ip_module_password','system_login','system_password')""")
    prov_ac = cur.fetchone()[0]

    total_a5 = 1 + 8 + len(levis_bids)

    print("\n=== Task 1 — RLS Schema dry-run ===")
    print(f"\nNew tables:")
    print(f"  employee_role              — role junction (multi-role capable)")
    print(f"  employee_building_assignment — {total_a5} A5 rows (JFME:1  SAHA:8  MACH:{len(levis_bids)})")
    print(f"  building_security_credential — {cred_count} buildings with at least one credential")
    print(f"    Sources: {cam_with_pw} camera rows with [populated] password")
    print(f"             {ac_with_creds} access_control rows with [populated] credential(s)")
    print(f"\nProvenance to update: {prov_cam} camera rows + {prov_ac} access_control rows")
    print(f"\nColumns to DROP (irreversible after write):")
    print(f"  building_camera_system.password")
    print(f"  building_access_control.ip_module_password, system_login, system_password")
    print(f"\nViews:")
    for name, _ in _VIEW_DDL:
        print(f"  {name}")
    print(f"\nA5 assignments ({total_a5} rows):")
    print(f"  JFME → [150]")
    print(f"  SAHA → {list(range(33, 41))}")
    print(f"  MACH → {levis_bids}  (sector_id 2+3)")

    if dry_run:
        print(f"\nDRY RUN — pass --write to commit.")
        conn.close()
        return

    # ── Write ─────────────────────────────────────────────────────────────────
    try:
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        # 1. Create tables
        print("\nCreating tables…")
        for stmt in _TABLE_DDL:
            cur.execute(stmt)
        conn.commit()
        cur = conn.cursor()

        # 2. Migrate credentials
        print("Migrating credentials…")
        cur.execute("""
            INSERT INTO building_security_credential
                (building_id, camera_password, access_ip_module_password,
                 access_system_login, access_system_password)
            SELECT
                COALESCE(bcs.building_id, bac.building_id),
                bcs.password,
                bac.ip_module_password,
                bac.system_login,
                bac.system_password
            FROM building_camera_system bcs
            FULL OUTER JOIN building_access_control bac ON bcs.building_id = bac.building_id
            WHERE bcs.password IS NOT NULL
               OR bac.ip_module_password IS NOT NULL
               OR bac.system_login IS NOT NULL
               OR bac.system_password IS NOT NULL
            ORDER BY COALESCE(bcs.building_id, bac.building_id)
        """)
        print(f"  {cur.rowcount} credential rows inserted.")

        # 3. Update provenance — camera password
        cur.execute("""
            UPDATE data_provenance dp
            SET target_table = 'building_security_credential',
                target_pk    = bsc.credential_id,
                target_column = 'camera_password'
            FROM building_camera_system bcs
            JOIN building_security_credential bsc ON bsc.building_id = bcs.building_id
            WHERE dp.target_table = 'building_camera_system'
              AND dp.target_column = 'password'
              AND dp.target_pk = bcs.camera_system_id
        """)
        prov_cam_n = cur.rowcount

        # 4. Update provenance — access_control columns
        for old_col, new_col in [
            ("ip_module_password", "access_ip_module_password"),
            ("system_login",       "access_system_login"),
            ("system_password",    "access_system_password"),
        ]:
            cur.execute(f"""
                UPDATE data_provenance dp
                SET target_table  = 'building_security_credential',
                    target_pk     = bsc.credential_id,
                    target_column = '{new_col}'
                FROM building_access_control bac
                JOIN building_security_credential bsc ON bsc.building_id = bac.building_id
                WHERE dp.target_table  = 'building_access_control'
                  AND dp.target_column = '{old_col}'
                  AND dp.target_pk     = bac.access_control_id
            """)
        print(f"  Provenance updated: {prov_cam_n} camera rows + access_control rows.")
        conn.commit()
        cur = conn.cursor()

        # 5. A5 employee_building_assignment (DROP happens separately via --drop flag)
        print("Inserting A5 assignments…")
        cur.execute("SELECT initials, employee_id FROM employee WHERE initials IN ('JFME','SAHA','MACH')")
        emp_map = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT building_id FROM building WHERE sector_id IN (2,3) ORDER BY building_id")
        mach_bids = [r[0] for r in cur.fetchall()]

        rows = []
        for initials, bids, atype, notes in _STATIC_A5 + [
            ("MACH", mach_bids, "a5_territory",
             "Rive-sud territory — all Lévis-sector buildings; territory-derived not building-listed"),
        ]:
            eid = emp_map[initials]
            for bid in bids:
                rows.append((eid, bid, atype, notes))

        execute_values(
            cur,
            """INSERT INTO employee_building_assignment (employee_id, building_id, assignment_type, notes)
               VALUES %s ON CONFLICT (employee_id, building_id) DO NOTHING""",
            rows, page_size=200,
        )
        print(f"  {len(rows)} assignment rows inserted.")

        # 7. Provenance for assignments
        cur.execute("SELECT assignment_id, building_id FROM employee_building_assignment ORDER BY assignment_id")
        assignments_written = cur.fetchall()
        pnum = prov_offset
        prov = []
        for assignment_id, building_id in assignments_written:
            pnum += 1
            prov.append((
                pnum, "employee_building_assignment", assignment_id, "building_id",
                "rls_setup", None, _SOURCE_FILE, None,
                None, None, str(building_id), str(building_id), None,
            ))
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
        cur = conn.cursor()
        print(f"  {len(prov)} provenance rows written.")

        # 8. Views
        print("Creating views…")
        for name, stmt in _VIEW_DDL:
            cur.execute(stmt)
            print(f"  {name}")
        conn.commit()

        # Final counts
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM building_security_credential")
        print(f"\nCommitted:")
        print(f"  building_security_credential: {cur.fetchone()[0]} rows")
        cur.execute("SELECT COUNT(*) FROM employee_building_assignment")
        print(f"  employee_building_assignment: {cur.fetchone()[0]} rows")
        cur.execute("SELECT COUNT(*) FROM data_provenance")
        print(f"  data_provenance total: {cur.fetchone()[0]}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv, drop_credentials="--drop" in sys.argv)
