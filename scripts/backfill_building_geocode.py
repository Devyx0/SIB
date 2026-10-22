#!/usr/bin/env python3
"""
scripts/backfill_building_geocode.py

One-time Nominatim geocode of building.adresse / ville / code_postal.

    uv run python scripts/backfill_building_geocode.py                  # dry-run, local
    uv run python scripts/backfill_building_geocode.py --apply          # write, local
    uv run python scripts/backfill_building_geocode.py --db remote      # dry-run only until you --apply
    uv run python scripts/backfill_building_geocode.py --db remote --apply

Defaults to buildings with null / pending geocode_status. Use --force to redo all.
Never run --db remote --apply without explicit permission.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.modules.portfolio.geocode import geocode_address  # noqa: E402

CSV_PATH = ROOT / "work" / "backfill_building_geocode_dryrun.csv"


def get_conn(db: str):
    if db == "local":
        return psycopg2.connect(
            host="localhost", port=54322,
            user="postgres", password="postgres", dbname="postgres",
        )
    load_dotenv(ROOT / ".env")
    return psycopg2.connect(
        host=os.environ["SUPABASE_HOST"],
        port=5432,
        user=f"postgres.{os.environ['SUPABASE_PROJECT_REF']}",
        password=os.environ["DATABASE_PASSWORD"],
        dbname="postgres", sslmode="require",
        options="-c statement_timeout=0",
    )


def fetch_buildings(conn, *, force: bool) -> list[dict]:
    cur = conn.cursor()
    if force:
        cur.execute(
            """
            SELECT building_id, adresse, ville, code_postal,
                   latitude, longitude, geocode_status
            FROM public.building
            ORDER BY building_id
            """
        )
    else:
        cur.execute(
            """
            SELECT building_id, adresse, ville, code_postal,
                   latitude, longitude, geocode_status
            FROM public.building
            WHERE geocode_status IS NULL
               OR geocode_status = 'pending'
               OR (geocode_status IN ('failed', 'needs_review') AND latitude IS NULL)
            ORDER BY building_id
            """
        )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "building_id", "adresse", "ville", "code_postal",
        "query", "status", "latitude", "longitude",
        "display_name", "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def apply_writes(conn, results: list[dict]) -> int:
    cur = conn.cursor()
    n = 0
    for r in results:
        cur.execute(
            """
            UPDATE public.building
            SET latitude = %s,
                longitude = %s,
                geocode_status = %s,
                geocode_query = %s,
                geocoded_at = now()
            WHERE building_id = %s
            """,
            (
                r["latitude"],
                r["longitude"],
                r["status"],
                r["query"] or None,
                r["building_id"],
            ),
        )
        n += 1
    conn.commit()
    cur.close()
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode building addresses via Nominatim")
    parser.add_argument("--apply", action="store_true", help="Write results to the DB")
    parser.add_argument("--db", choices=["local", "remote"], default="local")
    parser.add_argument("--force", action="store_true", help="Re-geocode every building")
    parser.add_argument("--limit", type=int, default=0, help="Cap buildings processed (0 = all)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"=== {mode} === [{args.db}]")
    if args.db == "remote":
        print("WARNING: targeting REMOTE Supabase. Writes only happen with --apply.")
    if args.apply and args.db == "remote":
        print("REMOTE APPLY — make sure you were given permission to write.")

    conn = get_conn(args.db)
    conn.autocommit = False
    buildings = fetch_buildings(conn, force=args.force)
    if args.limit and args.limit > 0:
        buildings = buildings[: args.limit]
    print(f"Buildings to geocode: {len(buildings)}")
    if not buildings:
        conn.close()
        return

    results: list[dict] = []
    counts: dict[str, int] = {}
    for i, b in enumerate(buildings, 1):
        result = geocode_address(b["adresse"], b["ville"], b["code_postal"])
        row = {
            "building_id": b["building_id"],
            "adresse": b["adresse"],
            "ville": b["ville"],
            "code_postal": b["code_postal"],
            "query": result.query,
            "status": result.status,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "display_name": result.display_name,
            "note": result.note,
        }
        results.append(row)
        counts[result.status] = counts.get(result.status, 0) + 1
        print(
            f"  [{i}/{len(buildings)}] #{b['building_id']} → {result.status}"
            + (f" ({result.note})" if result.note else "")
        )

    write_csv(results, CSV_PATH)
    print(f"\nCSV: {CSV_PATH}")
    print("Status counts:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    needs = [r for r in results if r["status"] in ("failed", "needs_review")]
    if needs:
        print(f"\nManual review candidates ({len(needs)}):")
        for r in needs[:30]:
            print(f"  #{r['building_id']} [{r['status']}] {r['query']!r} — {r['note']}")
        if len(needs) > 30:
            print(f"  … and {len(needs) - 30} more (see CSV)")

    if args.apply:
        n = apply_writes(conn, results)
        print(f"\nApplied: {n} buildings updated.")
    else:
        print("\nDry run only — re-run with --apply to write.")

    conn.close()


if __name__ == "__main__":
    main()
