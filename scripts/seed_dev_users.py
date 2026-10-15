#!/usr/bin/env python3
"""
Seed 4 Supabase Auth accounts for local development and link them to employee rows.

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

ACCOUNTS = [
    {"email": "coordinator@sib.local", "employee_id": 4},
    {"email": "director@sib.local",    "employee_id": 5},
    {"email": "technician@sib.local",  "employee_id": 24},
    {"email": "contractor@sib.local",  "employee_id": 20},
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
        for acct in ACCOUNTS:
            email, emp_id = acct["email"], acct["employee_id"]

            if email in existing:
                uid = existing[email]
                print(f"  {email}: already exists ({uid})")
            else:
                uid = _create_user(email, password)
                print(f"  {email}: created ({uid})")

            row = conn.execute(
                "SELECT auth_user_id FROM employee WHERE employee_id = %s",
                [emp_id],
            ).fetchone()

            current = str(row["auth_user_id"]) if row and row["auth_user_id"] else None
            if current == uid:
                print(f"    employee {emp_id}: already linked")
            else:
                conn.execute(
                    "UPDATE employee SET auth_user_id = %s WHERE employee_id = %s",
                    [uid, emp_id],
                )
                conn.commit()
                print(f"    employee {emp_id}: linked → {uid}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
