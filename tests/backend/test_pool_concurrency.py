"""Pool configuration and concurrency test.

Verifies that the pool is configured with adequate max_size and timeout so
40+ concurrent requests don't freeze the server (root cause of the 8-min freeze).
"""
from __future__ import annotations

import threading

import pytest


def test_pool_max_size_adequate():
    from backend.core.db import get_pool
    pool = get_pool()
    assert pool.max_size >= 10, (
        f"Pool max_size={pool.max_size} is too small — burst of 40 requests will freeze. "
        "Set max_size >= 10 in get_pool()."
    )


def test_pool_timeout_fast():
    from backend.core.db import get_pool
    pool = get_pool()
    # Fail fast at 5s instead of hanging 30s (old default)
    assert pool.timeout <= 10.0, (
        f"Pool timeout={pool.timeout}s is too long — exhausted pool will hang requests. "
        "Set timeout <= 10.0 in get_pool()."
    )


def test_pool_concurrent_connections():
    """10 simultaneous connections must all succeed without timeout."""
    from backend.core.db import get_pool
    pool = get_pool()
    results: list[str] = []
    lock = threading.Lock()

    def use_connection():
        try:
            with pool.connection() as conn:
                conn.execute("SELECT 1")
                with lock:
                    results.append("ok")
        except Exception as exc:
            with lock:
                results.append(f"err:{exc}")

    threads = [threading.Thread(target=use_connection) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8.0)

    assert len(results) == 10, f"Only {len(results)}/10 threads completed — possible deadlock"
    assert all(r == "ok" for r in results), f"Errors: {[r for r in results if r != 'ok']}"
