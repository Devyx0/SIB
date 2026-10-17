"""Root-level conftest — forces LOCAL_DB_NAME=sib_test before any backend module is imported.

This MUST be the first conftest loaded. pytest loads it before tests/backend/conftest.py,
which imports backend.core.db → backend.core.config → Settings(). By the time Settings()
runs, LOCAL_DB_NAME=sib_test is already in the environment, so the pool connects to the
test database and never touches the dev database (postgres).

Creating / syncing sib_test
---------------------------
One-time setup (run once per machine, or after schema changes):

    createdb -h localhost -p 54322 -U postgres sib_test
    psql   -h localhost -p 54322 -U postgres -d sib_test -f supabase/migrations/combined.sql

Where combined.sql is the concatenation of all files under supabase/migrations/ in
filename order. Alternatively apply them individually:

    for f in supabase/migrations/*.sql; do
        psql -h localhost -p 54322 -U postgres -d sib_test -f "$f"
    done

The sib_test DB contains schema only — no seed data. Tests insert and roll back their own
rows via the db_conn fixture (see tests/backend/conftest.py).
"""
import os

# Force — not setdefault — so that an accidentally exported LOCAL_DB_NAME cannot
# redirect tests at the dev database.
os.environ["LOCAL_DB_NAME"] = "sib_test"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _ensure_sib_test_db():
    """Assert that the test pool is connected to sib_test, then ensure required extensions."""
    import psycopg2
    from backend.core.config import settings

    assert settings.LOCAL_DB_NAME == "sib_test", (
        f"Tests must run against sib_test, but LOCAL_DB_NAME={settings.LOCAL_DB_NAME!r}. "
        "Do not override LOCAL_DB_NAME when running the test suite."
    )

    c = psycopg2.connect(
        host=settings.LOCAL_DB_HOST, port=settings.LOCAL_DB_PORT,
        user=settings.LOCAL_DB_USER, password=settings.LOCAL_DB_PASSWORD,
        dbname=settings.LOCAL_DB_NAME,
    )
    c.autocommit = True
    try:
        with c.cursor() as cur:
            # Sanity-check: the connected DB must actually be sib_test.
            cur.execute("SELECT current_database()")
            actual = cur.fetchone()[0]
            assert actual == "sib_test", (
                f"Connected to '{actual}' instead of 'sib_test'. "
                "Check LOCAL_DB_HOST/PORT match the local Supabase instance."
            )
            cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public;")
    finally:
        c.close()
