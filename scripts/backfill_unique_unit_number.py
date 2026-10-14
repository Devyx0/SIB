#!/usr/bin/env python3
"""
scripts/backfill_unique_unit_number.py

Walk unit → data_provenance (source_row) → MRR col B → unique_unit_number.
Ambiguity rules: skip Ancien/Ancienne keys; NULL if a unit maps to >1 key
or a key maps to >1 unit.

    uv run python scripts/backfill_unique_unit_number.py           # dry run, local
    uv run python scripts/backfill_unique_unit_number.py --apply   # write, local
    uv run python scripts/backfill_unique_unit_number.py --db remote --apply
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from drive_pipeline.ingestion.provenance import flush_to_db, log_provenance

MRR_PATH        = ROOT / "work" / "dryrun_maintenance" / "Master Rent Roll - All SIB Units.xlsx"
MRR_SOURCE_FILE = "Master Rent Roll - All SIB Units.xlsx"
MRR_SOURCE_TAB  = "Rent roll"
MRR_SOURCE_TYPE = "master_rent_roll"
MRR_KEY_COL     = 1                         # 0-indexed; column B = Unique Unit Number
ANCIEN_PREFIXES = ("Ancien ", "Ancienne ")

NAMED_CASES = [
    (1385, "1235-202 Colline (col77=blank, expect: set via provenance)"),
    (3709, "4875-3 Saint-Georges (stale col77, expect: set via provenance)"),
    (1638, "1625-207 Courtemanche bid=82 (expect: set unambiguously)"),
    (1669, "1675-207 Courtemanche bid=83 (expect: set unambiguously)"),
    (3126, "duplicate pair 4298-104 Roses (expect: NULL)"),
    (3127, "duplicate pair 4298-104 Roses (expect: set (current tenant))"),
    (3294, "duplicate pair 12085-310 Berlioz (expect: NULL)"),
    (3295, "duplicate pair 12085-310 Berlioz (expect: set (current tenant))"),
]


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


def load_mrr(path: Path) -> dict[int, str]:
    """Return {excel_row_number: unique_unit_number} for all non-blank MRR rows."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Rent roll"]
    result = {}
    for i, row in enumerate(ws.iter_rows(min_row=1, values_only=True)):
        excel_row = i + 1
        if excel_row == 1:
            continue  # header
        val = row[MRR_KEY_COL]
        if val is not None:
            result[excel_row] = str(val).strip()
    wb.close()
    return result


def build_maps(conn, mrr: dict[int, str]):
    """
    Returns:
      unit_to_all_rows — {unit_id: set of all MRR source_row ints}
      unit_to_keys     — {unit_id: set of non-Ancien candidate keys}
      key_to_units     — {key: set of unit_ids}
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT target_pk::int, source_row::int
        FROM   data_provenance
        WHERE  target_table = 'unit'
        AND    source_type  = 'master_rent_roll'
        AND    source_tab   = 'Rent roll'
        AND    source_row   IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()

    unit_to_all_rows: dict[int, set] = defaultdict(set)
    unit_to_keys:     dict[int, set] = defaultdict(set)

    for uid, rn in rows:
        unit_to_all_rows[uid].add(rn)
        key = mrr.get(rn)
        if key and not any(key.startswith(p) for p in ANCIEN_PREFIXES):
            unit_to_keys[uid].add(key)

    key_to_units: dict[str, set] = defaultdict(set)
    for uid, keys in unit_to_keys.items():
        for k in keys:
            key_to_units[k].add(uid)

    return dict(unit_to_all_rows), dict(unit_to_keys), dict(key_to_units)


def classify(all_units, unit_to_all_rows, unit_to_keys, key_to_units):
    """Returns {unit_id: (key_or_None, reason)}."""
    results = {}
    for uid in all_units:
        has_prov = uid in unit_to_all_rows
        keys = unit_to_keys.get(uid, set())

        if not has_prov:
            results[uid] = (None, "no_provenance")
        elif not keys:
            results[uid] = (None, "ancien_only")
        elif len(keys) > 1:
            results[uid] = (None, "ambiguous_unit_to_keys")
        else:
            key = next(iter(keys))
            if len(key_to_units.get(key, set())) > 1:
                results[uid] = (None, "ambiguous_key_to_units")
            else:
                results[uid] = (key, "set")
    return results


def print_report(results, all_units):
    counts: dict[str, int] = defaultdict(int)
    for _, (_, reason) in results.items():
        counts[reason] += 1

    print("─" * 60)
    print(f"  Total units                       : {len(all_units)}")
    print(f"  Will set unique_unit_number        : {counts['set']}")
    print(f"  NULL — no_provenance               : {counts['no_provenance']}")
    print(f"  NULL — ancien_only                 : {counts['ancien_only']}")
    print(f"  NULL — ambiguous unit→keys         : {counts['ambiguous_unit_to_keys']}")
    print(f"  NULL — ambiguous key→units         : {counts['ambiguous_key_to_units']}")
    print()

    samples = [(uid, key) for uid, (key, reason) in results.items() if key][:10]
    print("10 sample writes (unit_id → key):")
    for uid, key in samples:
        print(f"  {uid:>5}  {key!r}")
    print()

    print("Named cases:")
    for uid, label in NAMED_CASES:
        key, reason = results.get(uid, (None, "not_in_db"))
        print(f"  unit_id={uid:<5}  reason={reason:<26}  key={key!r}")
        print(f"            {label}")
    print("─" * 60)


def write_csv(results, all_units, path: Path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_id", "unique_unit_number", "reason"])
        for uid in all_units:
            key, reason = results[uid]
            w.writerow([uid, key or "", reason])
    print(f"CSV → {path}")


def post_apply_checks(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM unit WHERE unique_unit_number IS NOT NULL")
    n_set = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM data_provenance"
        " WHERE target_table='unit' AND target_column='unique_unit_number'"
    )
    n_prov = cur.fetchone()[0]
    cur.execute(
        "SELECT unit_id, unique_unit_number FROM unit"
        " WHERE unit_id IN (3126,3127,3294,3295) ORDER BY unit_id"
    )
    named = cur.fetchall()
    cur.close()
    print("\n--- post-apply checks ---")
    print(f"  units with unique_unit_number : {n_set}")
    print(f"  provenance rows (target=unit, col=unique_unit_number): {n_prov}")
    print("  duplicate-pair units:")
    for uid, key in named:
        print(f"    unit_id={uid}  key={key!r}")


def apply_writes(conn, results, unit_to_all_rows, mrr: dict[int, str]):
    """UPDATE unit + log_provenance + flush_to_db, single transaction."""
    to_write = [(uid, key) for uid, (key, reason) in results.items() if key]

    # Canonical source_row per unit: lowest non-Ancien row
    canonical_row: dict[int, int] = {}
    for uid, key in to_write:
        for rn in sorted(unit_to_all_rows[uid]):
            k = mrr.get(rn)
            if k and not any(k.startswith(p) for p in ANCIEN_PREFIXES):
                canonical_row[uid] = rn
                break

    cur = conn.cursor()
    for uid, key in to_write:
        rn = canonical_row[uid]
        cur.execute(
            "UPDATE public.unit SET unique_unit_number = %s WHERE unit_id = %s",
            (key, uid),
        )
        log_provenance(
            target_table="unit",
            target_pk=uid,
            target_column="unique_unit_number",
            source_type=MRR_SOURCE_TYPE,
            source_drive_id=None,
            source_file_name=MRR_SOURCE_FILE,
            source_tab=MRR_SOURCE_TAB,
            source_row=str(rn),
            source_column="Unique Unit Number",
            raw_value=key,
            ingested_value=key,
        )

    prov_count = flush_to_db(conn)
    conn.commit()
    cur.close()
    print(f"Applied: {len(to_write)} units written, {prov_count} provenance rows added.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db", choices=["local", "remote"], default="local")
    args = parser.parse_args()

    print(f"{'=== APPLY ===' if args.apply else '=== DRY RUN ==='} [{args.db}]")

    mrr = load_mrr(MRR_PATH)
    print(f"MRR rows loaded: {len(mrr)}")

    conn = get_conn(args.db)
    conn.autocommit = False

    cur = conn.cursor()
    cur.execute("SELECT unit_id FROM public.unit ORDER BY unit_id")
    all_units = [r[0] for r in cur.fetchall()]
    cur.close()
    print(f"Units in DB: {len(all_units)}\n")

    unit_to_all_rows, unit_to_keys, key_to_units = build_maps(conn, mrr)
    results = classify(all_units, unit_to_all_rows, unit_to_keys, key_to_units)

    print_report(results, all_units)

    csv_path = ROOT / "work" / "backfill_unit_number_dryrun.csv"
    write_csv(results, all_units, csv_path)

    if args.apply:
        apply_writes(conn, results, unit_to_all_rows, mrr)
        post_apply_checks(conn)

    conn.close()


if __name__ == "__main__":
    main()
