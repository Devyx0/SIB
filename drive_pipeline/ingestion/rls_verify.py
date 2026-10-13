"""
rls_verify.py — Verify RLS policies with simulated auth sessions.

Prerequisites (must all be applied before running):
  1. ingest_rls_schema.py --write  (tables + views created)
  2. ingest_employee_roles.py --write  (employee_role populated)
  3. rls_functions.sql applied in Supabase (current_employee_id, has_role, technician_building_ids)
  4. rls_policies.sql applied in Supabase

Method: sets auth_user_id on real employees, then simulates their JWT session
via SET LOCAL role + SET LOCAL "request.jwt.claims" inside rolled-back transactions.
No auth.users rows are created.

Run:
    uv run python -m drive_pipeline.ingestion.rls_verify
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import psycopg2
from drive_pipeline.ingestion.db import get_conn

# (initials, role_label, expected_mr_count_relation)
# VIBR is the technician under §5g review — sector_id=NULL means only own assigned MRs (14) are visible.
_TEST_CASES = [
    ("VIBR", "technician", "< total"),
    ("CALE", "coordinator", "= total"),
    ("CHBE", "director",    "= total"),
]

_TEST_UUIDS = {initials: uuid.uuid4() for initials, _, _ in _TEST_CASES}


def _jwt_claims(uid: uuid.UUID) -> str:
    return json.dumps({"sub": str(uid), "role": "authenticated"})


def _run_as(cur, uid: uuid.UUID, query: str) -> any:
    """Run query in a sub-transaction as the given auth uid. Returns raw result."""
    cur.execute("SAVEPOINT rls_test")
    try:
        cur.execute("SET LOCAL role = authenticated")
        cur.execute("SET LOCAL \"request.jwt.claims\" = %s", (_jwt_claims(uid),))
        cur.execute(query)
        result = cur.fetchall()
        cur.execute("ROLLBACK TO SAVEPOINT rls_test")
        cur.execute("RELEASE SAVEPOINT rls_test")
        return result
    except Exception as e:
        cur.execute("ROLLBACK TO SAVEPOINT rls_test")
        cur.execute("RELEASE SAVEPOINT rls_test")
        raise e


def run() -> None:
    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    # ── Look up employee_ids + total row counts ────────────────────────────────
    cur.execute("SELECT initials, employee_id FROM employee WHERE initials = ANY(%s)",
                (list(_TEST_UUIDS.keys()),))
    emp_map = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) FROM maintenance_request")
    total_mr = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM lease")
    total_lease = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM building")
    total_buildings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM building_security_credential")
    total_creds = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM employee")
    total_employees = cur.fetchone()[0]

    print(f"\n=== RLS Verification ===")
    print(f"Totals: MR={total_mr}, lease={total_lease}, buildings={total_buildings}, "
          f"creds={total_creds}, employees={total_employees}")

    missing = [i for i in _TEST_UUIDS if i not in emp_map]
    if missing:
        print(f"\nERROR: employees not found: {missing}")
        conn.close()
        sys.exit(1)

    # ── Set auth_user_id on test employees ────────────────────────────────────
    try:
        for initials, uid in _TEST_UUIDS.items():
            cur.execute("UPDATE employee SET auth_user_id = %s WHERE initials = %s",
                        (str(uid), initials))
        conn.commit()

        results = {}
        errors  = {}

        for initials, role_label, _ in _TEST_CASES:
            uid  = _TEST_UUIDS[initials]
            emp_id = emp_map[initials]
            row: dict = {}

            # Open a single transaction for all SET LOCAL queries for this user
            cur.execute("BEGIN")
            cur.execute("SET LOCAL role = authenticated")
            cur.execute("SET LOCAL \"request.jwt.claims\" = %s", (_jwt_claims(uid),))

            try:
                cur.execute("SELECT COUNT(*) FROM maintenance_request")
                row["mr"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM lease")
                row["lease"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM building")
                row["buildings"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM building_security_credential")
                row["creds"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM employee")
                row["employees"] = cur.fetchone()[0]

                # Column exclusion: urgency_tier must NOT exist in tech view
                try:
                    cur.execute("SELECT urgency_tier FROM maintenance_request_tech_view LIMIT 1")
                    row["view_col_exclusion"] = "FAIL — urgency_tier still visible"
                except psycopg2.errors.UndefinedColumn:
                    row["view_col_exclusion"] = "PASS"
                    conn.rollback()
                    # Re-open and re-auth for remaining queries
                    cur.execute("BEGIN")
                    cur.execute("SET LOCAL role = authenticated")
                    cur.execute("SET LOCAL \"request.jwt.claims\" = %s", (_jwt_claims(uid),))

            finally:
                conn.rollback()

            results[initials] = row

        # ── Print results ──────────────────────────────────────────────────────
        print(f"\n{'':6} {'maintenance_request':>20} {'lease':>8} {'buildings':>10} "
              f"{'creds':>7} {'employees':>10}  view_col_excl")
        print(f"{'':6} {'expected':>20} {'expected':>8} {'expected':>10} "
              f"{'expected':>7} {'expected':>10}")
        print("-" * 90)

        all_pass = True
        for initials, role_label, mr_rel in _TEST_CASES:
            row = results[initials]

            # Expected values
            exp_mr    = f"{mr_rel} {total_mr}" if mr_rel != "= total" else str(total_mr)
            exp_lease = str(total_lease) if role_label in ("director", "coordinator") else "0"
            exp_bldg  = str(total_buildings)
            exp_creds = str(total_creds) if role_label in ("admin", "director") else "0"
            exp_emp   = str(total_employees)

            # Actual
            act_mr    = row["mr"]
            act_lease = row["lease"]
            act_bldg  = row["buildings"]
            act_creds = row["creds"]
            act_emp   = row["employees"]

            # Pass/fail checks
            def chk(actual, expected_str, relation=None):
                if relation == "< total":
                    ok = actual < total_mr
                elif expected_str.isdigit():
                    ok = actual == int(expected_str)
                else:
                    ok = True  # can't evaluate
                return "✓" if ok else "✗", ok

            mr_sym, mr_ok     = chk(act_mr, exp_mr, mr_rel)
            lease_sym, l_ok   = chk(act_lease, exp_lease)
            bldg_sym, b_ok    = chk(act_bldg, exp_bldg)
            cr_sym, cr_ok     = chk(act_creds, exp_creds)
            emp_sym, e_ok     = chk(act_emp, exp_emp)
            vcol_ok = row.get("view_col_exclusion", "?") == "PASS"

            all_pass = all_pass and all([mr_ok, l_ok, b_ok, cr_ok, e_ok, vcol_ok])

            print(f"{initials:<6} ({role_label:<12})  "
                  f"MR:{act_mr:>6}{mr_sym}  lease:{act_lease:>4}{lease_sym}  "
                  f"bldg:{act_bldg:>3}{bldg_sym}  creds:{act_creds:>3}{cr_sym}  "
                  f"emp:{act_emp:>3}{emp_sym}  {row.get('view_col_exclusion','?')}")

        print("\n" + ("ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED"))

    finally:
        # Always clean up auth_user_id
        conn.rollback()
        cur2 = conn.cursor()
        cur2.execute("UPDATE employee SET auth_user_id = NULL WHERE initials = ANY(%s)",
                     (list(_TEST_UUIDS.keys()),))
        conn.commit()
        conn.close()
        print("auth_user_id cleaned up for test employees.")


if __name__ == "__main__":
    run()
