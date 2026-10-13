"""
DB connections.
  get_conn()        — psycopg3 sync pool, for new backend code
  get_legacy_conn() — psycopg2, for frozen triage (context_builder imports psycopg2.extras)
"""
from __future__ import annotations

import psycopg2
from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if settings.DATABASE_URL:
            conninfo = settings.DATABASE_URL
        else:
            conninfo = (
                f"host={settings.SUPABASE_HOST} port=5432"
                f" user=postgres.{settings.SUPABASE_PROJECT_REF}"
                f" password={settings.DATABASE_PASSWORD}"
                f" dbname=postgres sslmode=require"
            )
        _pool = ConnectionPool(conninfo, open=True)
    return _pool


def get_conn():
    """psycopg3 connection from the pool (context manager)."""
    return get_pool().connection()


def get_legacy_conn():
    """
    psycopg2 connection for frozen triage code.
    # ponytail: triage has import psycopg2.extras at module level; psycopg3 migration
    # waits until the triage freeze lifts.
    """
    return psycopg2.connect(
        host=settings.SUPABASE_HOST,
        port=5432,
        user=f"postgres.{settings.SUPABASE_PROJECT_REF}",
        password=settings.DATABASE_PASSWORD,
        dbname="postgres",
        sslmode="require",
        options="-c statement_timeout=0",
    )
