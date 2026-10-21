"""Self-issued ASNUF allocator (Postgres sequence)."""
from __future__ import annotations

from backend.modules.intake.asnu import next_asnu


def test_next_asnu_asnuf_from_zero_and_unique(db_conn):
    a = next_asnu(db_conn)
    b = next_asnu(db_conn)
    assert a.startswith("ASNUF") and b.startswith("ASNUF")
    assert a[5:].isdigit() and b[5:].isdigit()
    na, nb = int(a[5:]), int(b[5:])
    assert na >= 0
    assert nb == na + 1
    assert a != b
