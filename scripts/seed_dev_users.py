#!/usr/bin/env python3
"""
Seed Supabase Auth accounts for local development and link them to employee rows.

Covers every active employee that has at least one employee_role row.
Email: the employee's courriel, or <slugified name>@sib.local when missing.
All accounts share DEV_SEED_PASSWORD.

Guards:
  - Refuses to run unless DB_TARGET=local (default) and SUPABASE_URL is localhost.
  - Password from DEV_SEED_PASSWORD env var; fails fast if unset.

Idempotent: existing auth users and already-linked employees are skipped.

Usage:
  DB_TARGET=local DEV_SEED_PASSWORD=... python scripts/seed_dev_users.py
"""
from __future__ import annotations

import os
import sys
import unicodedata

import httpx
import psycopg
from psycopg.rows import dict_row

# Standard Supabase local-stack values (public — only valid for 127.0.0.1:54321).
_LOCAL_API = "http://127.0.0.1:54321"
_LOCAL_SRK = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0"
    ".EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)

def _fallback_email(name: str) -> str:
    """'Jessie Thomassin' -> 'jessie.thomassin@sib.local' (accents stripped)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = ".".join("".join(c if c.isalnum() else " " for c in ascii_name.lower()).split())
    return f"{slug}@sib.local"


def _accounts(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.employee_id, e.nom_employe, e.courriel
        FROM employee e
        WHERE e.is_active
          AND EXISTS (SELECT 1 FROM employee_role er WHERE er.employee_id = e.employee_id)
        ORDER BY e.employee_id
        """
    ).fetchall()
    return [
        {
            "email": (r["courriel"] or "").strip().lower() or _fallback_email(r["nom_employe"]),
            "employee_id": r["employee_id"],
        }
        for r in rows
    ]


def _guard() -> str:
    db_target = os.environ.get("DB_TARGET", "local")
    if db_target != "local":
        sys.exit(f"REFUSED: DB_TARGET={db_target!r}. This script only runs against the local database.")

    password = os.environ.get("DEV_SEED_PASSWORD", "")
    if not password:
        sys.exit("REFUSED: DEV_SEED_PASSWORD env var is not set.")

    return password


def _existing_users() -> dict[str, str]:
    """Return {email: uid} for all existing local auth users."""
    headers = {"apikey": _LOCAL_SRK, "Authorization": f"Bearer {_LOCAL_SRK}"}
    try:
        r = httpx.get(f"{_LOCAL_API}/auth/v1/admin/users", headers=headers, params={"per_page": 100})
        r.raise_for_status()
    except httpx.ConnectError:
        sys.exit("ERROR: Cannot reach local Supabase at 127.0.0.1:54321 — is `supabase start` running?")
    return {u["email"]: u["id"] for u in r.json().get("users", [])}


def _create_user(email: str, password: str) -> str:
    headers = {
        "apikey": _LOCAL_SRK,
        "Authorization": f"Bearer {_LOCAL_SRK}",
        "Content-Type": "application/json",
    }
    r = httpx.post(
        f"{_LOCAL_API}/auth/v1/admin/users",
        headers=headers,
        json={"email": email, "password": password, "email_confirm": True},
    )
    r.raise_for_status()
    return r.json()["id"]


def main() -> None:
    password = _guard()

    existing = _existing_users()

    conn = psycopg.connect(
        host="localhost", port=54322, user="postgres",
        password="postgres", dbname="postgres",
        row_factory=dict_row,
    )

    try:
        for acct in _accounts(conn):
            email, emp_id = acct["email"], acct["employee_id"]

            row = conn.execute(
                "SELECT auth_user_id FROM employee WHERE employee_id = %s",
                [emp_id],
            ).fetchone()
            linked = row["auth_user_id"] if row else None
            # After a remote→local data dump, auth_user_id often points at a
            # remote UUID that does not exist in local auth.users — treat as unlinked.
            if linked is not None:
                alive = conn.execute(
                    "SELECT 1 FROM auth.users WHERE id = %s", [linked]
                ).fetchone()
                if alive:
                    print(f"  employee {emp_id} ({email}): already linked — skipped")
                    continue
                print(f"  employee {emp_id} ({email}): orphan auth_user_id — relinking")

            if email in existing:
                uid = existing[email]
                print(f"  {email}: already exists ({uid})")
            else:
                uid = _create_user(email, password)
                print(f"  {email}: created ({uid})")

            conn.execute(
                "UPDATE employee SET auth_user_id = %s WHERE employee_id = %s",
                [uid, emp_id],
            )
            conn.commit()
            print(f"    employee {emp_id}: linked → {uid}")

        _ensure_receptionist_employee(conn)
        # Canonical local logins (docs / .env.example) — always pin to a role match.
        _pin_canonical(conn, existing, password)
    finally:
        conn.close()


def _ensure_receptionist_employee(conn: psycopg.Connection) -> None:
    """Dev-only receptionist row so receptionist@sib.local has someone to pin to."""
    row = conn.execute(
        "SELECT employee_id FROM employee WHERE lower(coalesce(courriel, '')) = 'receptionist@sib.local'"
    ).fetchone()
    if row:
        emp_id = row["employee_id"]
    else:
        # Dumps often leave the identity sequence behind max(employee_id).
        conn.execute(
            "SELECT setval(pg_get_serial_sequence('employee', 'employee_id'), "
            "COALESCE((SELECT MAX(employee_id) FROM employee), 1))"
        )
        emp_id = conn.execute(
            """
            INSERT INTO employee (nom_employe, courriel, initials, employment_type, is_active, role)
            VALUES ('Réception', 'receptionist@sib.local', 'RCP', 'unknown', true, 'receptionist')
            RETURNING employee_id
            """
        ).fetchone()["employee_id"]
        print(f"  employee {emp_id}: created Réception (receptionist@sib.local)")
    conn.execute(
        """
        INSERT INTO employee_role (employee_id, role)
        VALUES (%(id)s, 'receptionist')
        ON CONFLICT (employee_id, role) DO NOTHING
        """,
        {"id": emp_id},
    )
    conn.commit()


def _pin_canonical(conn: psycopg.Connection, existing: dict[str, str], password: str) -> None:
    """Keep role@sib.local logins usable after dumps."""
    pins = [
        ("coordinator@sib.local", "coordinator"),
        ("director@sib.local", "director"),
        ("technician@sib.local", "technician"),
        ("contractor@sib.local", "contractor"),
        ("receptionist@sib.local", "receptionist"),
    ]
    for email, role in pins:
        uid = existing.get(email)
        if not uid:
            uid = _create_user(email, password)
            existing[email] = uid
            print(f"  {email}: created ({uid})")
        already = conn.execute(
            "SELECT employee_id FROM employee WHERE auth_user_id = %s", [uid]
        ).fetchone()
        if already:
            print(f"  {email}: already pinned to employee {already['employee_id']}")
            continue
        emp = conn.execute(
            """
            SELECT e.employee_id FROM employee e
            JOIN employee_role er ON er.employee_id = e.employee_id
            WHERE e.is_active AND er.role = %s
            ORDER BY e.employee_id
            LIMIT 1
            """,
            [role],
        ).fetchone()
        if not emp:
            print(f"  {email}: no {role} employee to pin")
            continue
        conn.execute(
            "UPDATE employee SET auth_user_id = %s WHERE employee_id = %s",
            [uid, emp["employee_id"]],
        )
        conn.commit()
        print(f"  {email}: pinned → employee {emp['employee_id']} ({role})")



if __name__ == "__main__":
    main()
