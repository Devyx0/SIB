"""db.py — psycopg2 connection factory shared by all ingestion scripts."""
import os
import psycopg2

_PORT = 5432  # session pooler; safe for DDL and multi-statement txns


def get_conn(**kwargs):
    """Return a psycopg2 connection to Supabase Postgres. Requires DATABASE_PASSWORD,
    SUPABASE_HOST, and SUPABASE_PROJECT_REF in env."""
    # options=-c statement_timeout=0 disables the Supabase pooler's default statement timeout
    # so that bulk INSERTs and large SELECTs don't get cancelled mid-flight.
    conn = psycopg2.connect(
        host=os.environ["SUPABASE_HOST"],
        port=_PORT,
        user=f"postgres.{os.environ['SUPABASE_PROJECT_REF']}",
        password=os.environ["DATABASE_PASSWORD"],
        dbname="postgres", sslmode="require",
        options="-c statement_timeout=0",
        **kwargs,
    )
    return conn
