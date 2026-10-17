"""Pool concurrency test.

The original freeze: ConnectionPool.getconn() is a blocking call. When called
directly inside async BaseHTTPMiddleware.dispatch(), it blocks the event-loop
thread. A full pool causes all holders to stall (event loop is frozen), so
connections are never returned — permanent deadlock, not a queue drain.

Fix: asyncio.to_thread(pool.getconn) moves the wait off the event-loop thread.
The event loop stays free to resume existing holders, which finish, release
their connections, and unblock the waiting acquirers.

Tests:
  1. Pool config is adequate for production.
  2. 50 concurrent requests against pool capped at max_size=4 all return 200
     — no 503, no hang. Proves queue-drain, not deadlock.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.core.config import settings


def test_pool_max_size_adequate():
    from backend.core.db import get_pool
    pool = get_pool()
    assert pool.max_size >= 10, (
        f"Pool max_size={pool.max_size} is too small for production bursts. "
        "Set max_size >= 10 in get_pool()."
    )


def test_pool_timeout_set():
    from backend.core.db import get_pool
    pool = get_pool()
    assert pool.timeout is not None and pool.timeout >= 5.0, (
        f"Pool timeout={pool.timeout}s — should be at least 5s."
    )


def test_50_concurrent_requests_max_size_4_all_200():
    """50 concurrent GET /health requests with pool capped at 4 slots must all return 200.

    With the old sync getconn() in dispatch(), a pool of 4 deadlocks here.
    With asyncio.to_thread(), waiters yield the event loop, holders finish,
    and the queue drains — all 50 return 200.
    """
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from backend.core import db as db_module
    from backend.main import create_app

    # Build a fresh pool with max_size=4; patch it in for this test.
    if settings.DB_TARGET == "local":
        conninfo = (
            f"host={settings.LOCAL_DB_HOST} port={settings.LOCAL_DB_PORT}"
            f" user={settings.LOCAL_DB_USER} password={settings.LOCAL_DB_PASSWORD}"
            f" dbname={settings.LOCAL_DB_NAME}"
        )
    else:
        pytest.skip("Concurrency test requires local DB")

    small_pool = ConnectionPool(
        conninfo, open=True,
        min_size=1, max_size=4, timeout=30.0,
        kwargs={"row_factory": dict_row},
    )
    original_pool = db_module._pool
    db_module._pool = small_pool

    try:
        async def _run():
            app = create_app()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await asyncio.gather(
                    *[client.get("/health") for _ in range(50)]
                )

        responses = asyncio.run(_run())
    finally:
        db_module._pool = original_pool
        small_pool.close()

    statuses = [r.status_code for r in responses]
    non_200 = [s for s in statuses if s != 200]
    assert not non_200, (
        f"{len(non_200)}/50 requests returned non-200: {set(non_200)}\n"
        "Likely cause: pool acquisition is still blocking the event loop."
    )
