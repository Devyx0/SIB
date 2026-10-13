"""
repatch_building_ids.py — Re-parse raw_title with the updated title parser and
patch building_id / project_id / sector_id / civic / street_raw on
maintenance_request rows where the result improves.

Does NOT re-translate prose fields and does NOT re-fetch from Google Calendar.
Run:
    uv run python -m drive_pipeline.ingestion.repatch_building_ids
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.parse_calendar_requests import _parse_title, _match_building


def _load_live(conn):
    cur = conn.cursor()
    cur.execute("SELECT building_id, adresse, project_id, sector_id FROM building")
    live_bldg: dict[str, dict] = {}
    for bid, adresse, pid, sid in cur.fetchall():
        live_bldg[adresse] = {"building_id": bid, "project_id": pid, "sector_id": sid}
    cur.execute("SELECT project_id, nom_unique_projet FROM project")
    live_proj: dict[str, int] = {nom.lower(): pid for pid, nom in cur.fetchall()}
    return live_bldg, live_proj


def _resolve(street, civic, project_label, live_bldg, live_proj):
    """Call _match_building → look up live building_id."""
    if not street and not civic:
        return None, None, None
    row = _match_building(street, civic, project_label)
    if not row:
        return None, None, None
    tf_match = row.get("unique_building_name")
    b = live_bldg.get(tf_match)
    if not b:
        return None, None, None
    building_id = b["building_id"]
    project_id = b["project_id"]
    sector_id = b["sector_id"]
    if project_label:
        pid = live_proj.get(project_label.lower())
        if pid:
            project_id = pid
    return building_id, project_id, sector_id


def _patch():
    conn = get_conn()
    live_bldg, live_proj = _load_live(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT request_id, raw_title, building_id, project_id, sector_id,
               civic, street_raw, project_label
        FROM maintenance_request
        WHERE raw_title IS NOT NULL
        ORDER BY request_id
    """)
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} rows from maintenance_request.")

    filled = 0      # NULL building_id → non-NULL
    changed = 0     # non-NULL building_id → different non-NULL (regression candidate)
    civic_filled = 0
    unchanged = 0
    updates: list[tuple] = []

    for (request_id, raw_title, old_bid, old_pid, old_sid,
         old_civic, old_street, project_label) in rows:

        tf = _parse_title(str(raw_title))
        new_civic = tf.get("civic")
        new_street = tf.get("street")

        new_bid, new_pid, new_sid = _resolve(
            new_street, new_civic, project_label, live_bldg, live_proj
        )

        bid_changed = new_bid != old_bid
        # Only fill civic when it was previously null and is now non-null
        civic_improved = new_civic is not None and old_civic is None

        if not bid_changed and not civic_improved:
            unchanged += 1
            continue

        if bid_changed:
            if old_bid is None and new_bid is not None:
                filled += 1
            elif old_bid is not None and new_bid is not None and new_bid != old_bid:
                changed += 1
                title_s = str(raw_title)[:80]
                print(f"  REGRESSION? rid={request_id} {old_bid}→{new_bid} {title_s!r}")

        if civic_improved:
            civic_filled += 1

        updates.append((
            new_bid,   new_pid,  new_sid,
            new_civic, new_street,
            request_id,
        ))

    print(f"\nPatch plan: {len(updates)} rows to update")
    print(f"  building_id NULL→non-NULL:  {filled}")
    print(f"  building_id non-NULL→other: {changed}  (listed above)")
    print(f"  civic filled (was null):    {civic_filled}")
    print(f"  unchanged:                  {unchanged}")

    if not updates:
        print("Nothing to patch.")
        conn.close()
        return

    _SQL = """
        UPDATE maintenance_request
        SET building_id = COALESCE(%s, building_id),
            project_id  = COALESCE(%s, project_id),
            sector_id   = COALESCE(%s, sector_id),
            civic       = COALESCE(%s, civic),
            street_raw  = COALESCE(%s, street_raw)
        WHERE request_id = %s
    """
    cur.executemany(_SQL, updates)
    conn.commit()
    print("\nCommitted.")

    # Post-patch coverage
    cur.execute("SELECT COUNT(*) FROM maintenance_request WHERE building_id IS NOT NULL")
    matched = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM maintenance_request")
    total = cur.fetchone()[0]
    print(f"\nPost-patch building coverage: {matched}/{total} ({matched/total*100:.1f}%)")

    cur.execute("""
        SELECT parse_status,
               COUNT(*) AS n,
               SUM(CASE WHEN building_id IS NULL THEN 1 ELSE 0 END) AS nulls
        FROM maintenance_request
        GROUP BY parse_status ORDER BY parse_status
    """)
    print("\nNull building_id by parse_status after patch:")
    for ps, n, nulls in cur.fetchall():
        print(f"  {ps}: {nulls} null / {n} total")

    conn.close()


if __name__ == "__main__":
    _patch()
