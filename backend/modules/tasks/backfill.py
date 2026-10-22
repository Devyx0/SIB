"""Python entry point for the open-request → dispatch_task backfill.

The logic lives in SQL (`public.backfill_open_requests()`, created by migration
20261022140000_dispatch_task_backfill.sql) so the migration and tests share one
implementation.
"""
from __future__ import annotations


def backfill_open_requests(conn) -> int:
    """Give every open pre-cutover request one accepted task. Returns requests migrated.

    Idempotent: requests that already have a task are skipped.
    """
    return conn.execute("SELECT public.backfill_open_requests() AS n").fetchone()["n"]
