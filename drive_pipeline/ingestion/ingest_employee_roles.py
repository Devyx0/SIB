"""
ingest_employee_roles.py — Populate employee_role from employee table.

Role rules (applied in order):
  CHBE                              → director
  CALE, CHGE, PISI, SETO, DISP     → coordinator
  employment_type='staff', not above → technician
  employment_type='contractor_company' → contractor
  employment_type='unknown', not in above → skipped (logged)

Run:
    uv run python -m drive_pipeline.ingestion.ingest_employee_roles          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_employee_roles --write  # write
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

_DIRECTOR    = {"CHBE"}
_COORDINATOR = {"CALE", "CHGE", "PISI", "SETO", "DISP"}
_SOURCE_FILE = "rls-proposal-v2.md"


def _assign_role(initials: str, employment_type: str) -> str | None:
    if initials in _DIRECTOR:
        return "director"
    if initials in _COORDINATOR:
        return "coordinator"
    if employment_type == "staff":
        return "technician"
    if employment_type == "contractor_company":
        return "contractor"
    return None  # employment_type='unknown' and not in any named set


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT employee_id, initials, employment_type FROM employee ORDER BY employee_id")
    employees = cur.fetchall()

    assignments: list[tuple[int, str, str, str]] = []  # (emp_id, initials, emp_type, role)
    skipped:     list[tuple[int, str, str]] = []

    for emp_id, initials, emp_type in employees:
        role = _assign_role(initials, emp_type)
        if role:
            assignments.append((emp_id, initials, emp_type, role))
        else:
            skipped.append((emp_id, initials, emp_type))

    print("\n=== Task 2 — employee_role population ===")
    print(f"\n{'initials':<6} {'employment_type':<22} {'→ role'}")
    print(f"{'-'*6} {'-'*22} {'-'*15}")
    for emp_id, initials, emp_type, role in assignments:
        print(f"  {initials:<6} {emp_type:<22} {role}")
    if skipped:
        print(f"\nSkipped (no role assigned — employment_type='unknown', not in named coordinator/director sets):")
        for emp_id, initials, emp_type in skipped:
            print(f"  {initials:<6} {emp_type}")
    print(f"\nTotal: {len(assignments)} role rows, {len(skipped)} skipped.")

    if dry_run:
        print("\nDRY RUN — pass --write to commit.")
        conn.close()
        return

    try:
        cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
        prov_offset = cur.fetchone()[0]

        execute_values(
            cur,
            """INSERT INTO employee_role (employee_id, role) VALUES %s
               ON CONFLICT (employee_id, role) DO NOTHING""",
            [(emp_id, role) for emp_id, _, _, role in assignments],
            page_size=100,
        )
        conn.commit()
        cur = conn.cursor()

        # Fetch back role_ids for provenance
        cur.execute("""
            SELECT er.employee_role_id, er.employee_id, er.role
            FROM employee_role er ORDER BY er.employee_role_id
        """)
        role_rows = cur.fetchall()

        pnum = prov_offset
        prov = []
        for role_id, emp_id, role in role_rows:
            pnum += 1
            prov.append((
                pnum, "employee_role", role_id, "role",
                "rls_setup", None, _SOURCE_FILE, None,
                emp_id, None,    # source_row = employee_id for traceability
                role, role, None,
            ))

        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov, page_size=100,
        )
        conn.commit()
        print(f"\nCommitted: {len(role_rows)} employee_role rows, {len(prov)} provenance rows.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
