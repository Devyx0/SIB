"""Self-issued request IDs for app intake (replaces Gravity ASNU).

Format: ASNUF0, ASNUF1, … via Postgres sequence `asnu_seq`.
Concurrent nextval() never collides; UNIQUE index is the backstop.
"""
from __future__ import annotations

_PREFIX = "ASNUF"


def next_asnu(conn) -> str:
    """Allocate the next ASNUF##### (starts at ASNUF0)."""
    row = conn.execute("SELECT nextval('asnu_seq') AS n").fetchone()
    return f"{_PREFIX}{int(row['n'])}"
