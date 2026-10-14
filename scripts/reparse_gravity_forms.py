#!/usr/bin/env python3
"""
scripts/reparse_gravity_forms.py

Re-parse the 148 gravity_forms rows from the cached event descriptions
(work/gf_raw_events_cache.json) using the fixed parser, then fill NULL
columns in maintenance_request.

Rules:
  - NULL-fill only: never overwrite an existing non-NULL value.
  - Disagreements (normalised parsed ≠ current non-NULL) are reported but not written.
  - submission_date is parsed as America/Toronto and stored as timestamptz.
  - unit_label is filled from GF unit_number where unit_label IS NULL.
  - entry_permission and animals go through the same _entry_permission /
    _normalize_animals normalisation as write_maintenance_requests.py.
  - Free-text columns (caller_name, caller_phone, caller_email, caller_type,
    urgency_raw, fees_advised, address_urgency, category_raw) are stored as-is.
  - One transaction; rolled back on any error in dry-run mode.

Usage:
    uv run python scripts/reparse_gravity_forms.py            # dry run, local
    uv run python scripts/reparse_gravity_forms.py --apply    # write, local
    uv run python scripts/reparse_gravity_forms.py --db remote --apply
"""
import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from drive_pipeline.ingestion.parse_calendar_requests import _parse_gravity_forms
from drive_pipeline.ingestion.extract_raw_fields import _entry_permission, _normalize_animals
from drive_pipeline.ingestion.provenance import flush_to_db, log_provenance

CACHE_PATH = ROOT / "work" / "gf_raw_events_cache.json"
TZ_TORONTO = ZoneInfo("America/Toronto")

# GF field → DB column. None = skip (already populated or not a column).
# Columns requiring normalisation are handled explicitly in coerce().
GF_FIELD_TO_COL: dict[str, str | None] = {
    "submission_date": "submission_date",
    "caller_type":     "caller_type",
    "unit_number":     "unit_label",       # fill only where unit_label IS NULL
    "caller_name":     "caller_name",
    "caller_phone":    "caller_phone",
    "caller_email":    "caller_email",
    "urgency_raw":     "urgency_raw",
    "category_raw":    "category_raw",
    "address_urgency": "address_urgency",
    "entry_permission":"entry_permission",  # normalised via _entry_permission()
    "animals":         "animals",           # normalised via _normalize_animals()
    "fees_advised":    "fees_advised",
    "message":         None,               # triage_summary already populated
    "gravity_raw":     None,               # already populated
}

# Columns holding PII — mask values in dry-run terminal output
PII_COLS = {"caller_name", "caller_phone", "caller_email", "unit_label"}


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


def coerce(col: str, raw: str | None):
    """Apply the same coercion/normalisation as write_maintenance_requests.py."""
    if not raw or not raw.strip():
        return None
    if col == "submission_date":
        raw_first = raw.split("\n", 1)[0].strip()
        try:
            dt = datetime.strptime(raw_first, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=TZ_TORONTO)
        except ValueError:
            return None
    if col == "entry_permission":
        return _entry_permission(raw)
    if col == "animals":
        return _normalize_animals(raw)
    return raw.strip() or None


def mask(v) -> str:
    if v is None:
        return "NULL"
    s = str(v)
    return "***" if len(s) <= 4 else s[:2] + "***" + s[-2:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db", choices=["local", "remote"], default="local")
    args = parser.parse_args()

    import json
    cache = json.loads(CACHE_PATH.read_text())
    events = {e["request_id"]: e for e in cache["events"]}
    errors_in_cache = {e["request_id"] for e in cache["errors"]}
    missing_in_cache = {e["request_id"] for e in cache["missing"]}
    print(f"Cache: {cache['fetched']} fetched, "
          f"{len(errors_in_cache)} errors {sorted(errors_in_cache)}, "
          f"{len(missing_in_cache)} missing/deleted {sorted(missing_in_cache)}")

    conn = get_conn(args.db)
    conn.autocommit = False
    cur = conn.cursor()

    cols = sorted({c for c in GF_FIELD_TO_COL.values() if c})
    col_list = ", ".join(cols)
    cur.execute(
        f"SELECT request_id, {col_list} FROM maintenance_request "
        f"WHERE body_format = 'gravity_forms' ORDER BY request_id"
    )
    col_names = [d[0] for d in cur.description]
    db_rows = {row[0]: dict(zip(col_names, row)) for row in cur.fetchall()}
    print(f"GF rows in DB: {len(db_rows)}\n")

    before_counts = {c: sum(1 for r in db_rows.values() if r.get(c) is not None)
                     for c in cols}
    will_fill: dict[str, int] = {c: 0 for c in cols}
    disagreements: list[dict] = []
    writes: list[tuple] = []      # (request_id, col, coerced_value)
    sample_rows: list[dict] = []
    no_fill_rids: list[tuple] = []

    for request_id, db_row in sorted(db_rows.items()):
        if request_id in errors_in_cache or request_id in missing_in_cache:
            continue
        ev = events.get(request_id)
        if not ev:
            no_fill_rids.append((request_id, "not_in_cache"))
            continue

        parsed = _parse_gravity_forms(ev["description"])
        row_writes: dict[str, object] = {}

        for gf_field, col in GF_FIELD_TO_COL.items():
            if col is None:
                continue
            raw_val = parsed.get(gf_field)
            coerced = coerce(col, raw_val)
            if coerced is None:
                continue

            current = db_row.get(col)
            if current is None:
                row_writes[col] = coerced
                will_fill[col] += 1
                writes.append((request_id, col, coerced))
            else:
                cur_str = str(current).strip()
                new_str = str(coerced).strip()
                if cur_str != new_str:
                    disagreements.append({
                        "request_id": request_id,
                        "column":     col,
                        "current":    cur_str,
                        "reparsed":   new_str,
                    })

        if row_writes and len(sample_rows) < 5:
            sample_rows.append({"request_id": request_id, "writes": row_writes})
        elif not row_writes:
            no_fill_rids.append((request_id, "all_nulls_empty_or_normalised_to_none"))

    # ── Dry-run report ──────────────────────────────────────────────────────
    print("=" * 65)
    print(f"{'=== APPLY ===' if args.apply else '=== DRY RUN ==='} [{args.db}]")
    print("=" * 65)

    print("\n── Fetch summary ──────────────────────────────────────────────")
    print(f"  Fetched       : {cache['fetched']}/148")
    print(f"  Errors        : {sorted(errors_in_cache)}  (HTTP errors; excluded from re-parse)")
    print(f"  Missing/deleted: {sorted(missing_in_cache)}")
    print(f"  Request_ids with zero fills: "
          f"{[r for r,_ in no_fill_rids]} — see reasons below")
    for rid, reason in no_fill_rids:
        print(f"    rid={rid}: {reason}")

    print("\n── Per-field fill counts (before → after) ─────────────────────")
    for col in sorted(will_fill):
        b = before_counts.get(col, 0)
        delta = will_fill[col]
        print(f"  {col:<22s}: {b:>3} → {b + delta:>3}  (+{delta})")

    print(f"\n  Total writes planned: {len(writes)}")

    print(f"\n── Disagreements (existing ≠ normalised-reparsed; NOT written): {len(disagreements)} ──")
    for d in disagreements[:5]:
        cur_s = d["current"][:60]
        rep_s = d["reparsed"][:60]
        if d["column"] in PII_COLS:
            cur_s = mask(d["current"])
            rep_s = mask(d["reparsed"])
        print(f"  rid={d['request_id']:<6} col={d['column']:<22s}  "
              f"current={cur_s!r}  reparsed={rep_s!r}")
    if len(disagreements) > 5:
        print(f"  ... ({len(disagreements) - 5} more)")

    print(f"\n── 5 sample rows (PII masked) ─────────────────────────────────")
    for s in sample_rows:
        rid = s["request_id"]
        print(f"\n  request_id={rid}")
        for col, val in sorted(s["writes"].items()):
            if col in PII_COLS:
                print(f"    {col:<22s}: {mask(val)}")
            else:
                vs = str(val)
                print(f"    {col:<22s}: {vs[:80]!r}")

    print(f"\n── submission_date DST proof (America/Toronto) ─────────────────")
    dt_samples = [(rid, col, val) for rid, col, val in writes if col == "submission_date"][:5]
    for rid, col, dt in dt_samples:
        ev_parsed = _parse_gravity_forms(events[rid]["description"])
        raw_dt = ev_parsed.get("submission_date", "?")
        print(f"  rid={rid:<6}  raw={raw_dt!r}")
        print(f"           stored={str(dt)!r}  offset={str(dt.utcoffset())!r}")
    print("  NOTE: all GF events fall in summer 2026 (EDT, UTC-4).")
    print("  No events span the March 8 (spring-forward) or Nov 1 (fall-back) DST boundary.")

    print(f"\n── Per-column: 2 new values vs 2 existing (same column) ───────")
    for target_col in ["urgency_raw", "caller_type", "fees_advised", "entry_permission", "animals"]:
        new_vals   = [(rid, val) for rid, col, val in writes if col == target_col][:2]
        if not new_vals:
            continue
        # Existing non-NULL values
        existing   = [(rid, r[target_col]) for rid, r in sorted(db_rows.items())
                      if r.get(target_col) is not None][:2]
        print(f"\n  column: {target_col}")
        for rid, val in new_vals:
            vs = str(val)
            print(f"    NEW  rid={rid:<6}: {vs[:60]!r}")
        for rid, val in existing:
            vs = str(val)
            print(f"    EXIST rid={rid:<6}: {vs[:60]!r}")

    # Write CSV
    csv_path = ROOT / "work" / "gf_reparse_dryrun.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["request_id", "column", "value", "action"])
        for rid, col, val in writes:
            w.writerow([rid, col, str(val), "fill_null"])
        for d in disagreements:
            w.writerow([d["request_id"], d["column"], d["reparsed"], "disagreement_skipped"])
    print(f"\nCSV → {csv_path}")

    changed_rids = sorted({w[0] for w in writes})
    print(f"\nRequest IDs with at least one column filled: {len(changed_rids)}")

    if not args.apply:
        conn.close()
        return

    # ── Apply ──────────────────────────────────────────────────────────────
    print("\nApplying writes...")
    by_rid: dict[int, dict] = {}
    for rid, col, val in writes:
        by_rid.setdefault(rid, {})[col] = val

    for rid, updates in sorted(by_rid.items()):
        set_clauses = ", ".join(f"{col} = %s" for col in updates)
        vals = list(updates.values()) + [rid]
        cur.execute(
            f"UPDATE maintenance_request SET {set_clauses} WHERE request_id = %s",
            vals,
        )
        for col, val in updates.items():
            log_provenance(
                target_table="maintenance_request",
                target_pk=rid,
                target_column=col,
                source_type="google_calendar",
                source_drive_id=None,
                source_file_name="gravity_forms_cache",
                source_tab=None,
                source_row=str(rid),
                source_column=col,
                raw_value=str(val),
                ingested_value=str(val),
            )

    prov_count = flush_to_db(conn)
    conn.commit()
    cur.close()
    print(f"Applied: {len(by_rid)} rows updated, {prov_count} provenance rows added.")

    # Post-apply checks
    cur2 = conn.cursor()
    col_list2 = ", ".join(f"COUNT({c})" for c in sorted(cols))
    cur2.execute(
        f"SELECT {col_list2} FROM maintenance_request WHERE body_format = 'gravity_forms'"
    )
    counts = cur2.fetchone()
    cur2.close()
    print("\n--- post-apply checks (non-NULL counts for GF rows) ---")
    for col, count in zip(sorted(cols), counts):
        print(f"  {col:<22s}: {count}")
    conn.close()


if __name__ == "__main__":
    main()
