"""
ingest_tf_finance.py — Fill finance cluster columns on project from live TF.

New columns written (all on project — grain confirmed project-level 2026-10-06):
  purchase_price   numeric   TF col 14 "Prix d'achat"
  acquisition_date date      TF col 15 "Date d'acquisition"
  quickbooks_class varchar   TF col 5  "Nom de Classe pour Quickbooks"

Only writes cells that are currently NULL (idempotent).

Skips:
  - TF footer row (nom_unique_projet is None or 'TOTAL')
  - TF projects with no matching project_id in DB (e.g. Hypolite-Bernier 843)
  - Prix d'achat = 'N/A' → stored as NULL

Place de l'Entente quickbooks_class: TF has a 2:2 tie from a known QuickBooks
numbering overlap (§5d). The contaminated value ('4032-4040, rue du Confluent')
is shared with the Confluent project; the correct value for Place de l'Entente
contains 'rue Saint-Georges'. The contaminated value is excluded.

Run:
    uv run python -m drive_pipeline.table_fondamentale.ingest_tf_finance          # dry run
    uv run python -m drive_pipeline.table_fondamentale.ingest_tf_finance --write
"""
from __future__ import annotations

import datetime
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.table_fondamentale.ingest_tf_phase1 import (
    _download_tf, _TF_FILE_ID, _TF_FILE_NAME, _TF_TAB,
)

WRITE = "--write" in sys.argv

_COL_PROJ   = 1   # Nom Unique de Projet
_COL_BLDG   = 6   # Nom Unique d'Immeuble
_COL_CLS    = 5   # Nom de Classe pour Quickbooks
_COL_PRIX   = 14  # Prix d'achat
_COL_DATE   = 15  # Date d'acquisition


def _parse_price(val) -> float | None:
    if val is None or str(val).strip().upper() == "N/A":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_date(val) -> datetime.date | None:
    if val is None:
        return None
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.date() if isinstance(val, datetime.datetime) else val
    return None


def _pick_class(classes: list[str]) -> str | None:
    """Mode of non-null classes. Breaks 2:2 ties by excluding values that
    contain 'rue du Confluent' when at least one alternative exists."""
    non_null = [c for c in classes if c and str(c) != "None"]
    if not non_null:
        return None
    counts = Counter(non_null)
    if len(counts) == 1:
        return counts.most_common(1)[0][0]
    # Tie or conflict: exclude Confluent contamination if alternatives exist
    cleaned = [c for c in non_null if "rue du Confluent" not in c]
    if cleaned:
        return Counter(cleaned).most_common(1)[0][0]
    return counts.most_common(1)[0][0]


def main() -> None:
    rows = _download_tf()
    data = rows[1:]  # skip header

    # Aggregate per project name
    by_proj: dict[str, dict] = defaultdict(lambda: {"prices": [], "dates": [], "classes": [], "bldgs": []})
    for r in data:
        proj = r[_COL_PROJ]
        if not proj or str(proj).strip().upper() in ("TOTAL", "NONE"):
            continue
        p = str(proj).strip()
        by_proj[p]["prices"].append(_parse_price(r[_COL_PRIX]))
        by_proj[p]["dates"].append(_parse_date(r[_COL_DATE]))
        by_proj[p]["classes"].append(r[_COL_CLS])
        by_proj[p]["bldgs"].append(r[_COL_BLDG])

    # Resolve per-project canonical values
    project_vals: dict[str, dict] = {}
    for proj, agg in by_proj.items():
        prices = [p for p in agg["prices"] if p is not None]
        dates  = [d for d in agg["dates"]  if d is not None]
        price  = prices[0] if prices else None   # confirmed all same within project
        date   = dates[0]  if dates  else None   # confirmed all same within project
        cls    = _pick_class([str(c) for c in agg["classes"]])
        project_vals[proj] = {"price": price, "date": date, "cls": cls}

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT project_id, nom_unique_projet, purchase_price, acquisition_date, quickbooks_class FROM project")
    db_rows = {nom: {"pid": pid, "price": pp, "date": ad, "cls": qc}
               for pid, nom, pp, ad, qc in cur.fetchall()}

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    next_prov = cur.fetchone()[0] + 1

    price_updates:  list[tuple] = []
    date_updates:   list[tuple] = []
    cls_updates:    list[tuple] = []
    skipped_no_db:  list[str]   = []
    skipped_set:    int = 0

    for proj_name, vals in sorted(project_vals.items()):
        db = db_rows.get(proj_name)
        if db is None:
            skipped_no_db.append(proj_name)
            continue
        pid = db["pid"]

        if vals["price"] is not None and db["price"] is None:
            price_updates.append((pid, vals["price"], proj_name))
        elif db["price"] is not None:
            skipped_set += 1

        if vals["date"] is not None and db["date"] is None:
            date_updates.append((pid, vals["date"], proj_name))
        elif db["date"] is not None:
            skipped_set += 1

        if vals["cls"] is not None and db["cls"] is None:
            cls_updates.append((pid, vals["cls"], proj_name))
        elif db["cls"] is not None:
            skipped_set += 1

    print(f"\n=== ingest_tf_finance {'DRY RUN' if not WRITE else 'WRITE'} ===")
    print(f"TF projects:          {len(project_vals)}")
    print(f"DB projects:          {len(db_rows)}")
    print(f"Skipped (not in DB):  {len(skipped_no_db)} — {skipped_no_db}")
    print(f"Skipped (already set):{skipped_set}")
    print()
    print(f"purchase_price updates:   {len(price_updates)}")
    print(f"acquisition_date updates: {len(date_updates)}")
    print(f"quickbooks_class updates: {len(cls_updates)}")
    print()
    print("Sample purchase_price (first 10):")
    for pid, price, name in price_updates[:10]:
        print(f"  project_id={pid:3d} {name!r}: {price}")
    print()
    print("Sample acquisition_date (first 5):")
    for pid, date, name in date_updates[:5]:
        print(f"  project_id={pid:3d} {name!r}: {date}")
    print()
    print("Sample quickbooks_class (first 5):")
    for pid, cls, name in cls_updates[:5]:
        print(f"  project_id={pid:3d} {name!r}: {cls!r}")

    if not WRITE:
        print("\nDRY RUN — pass --write to commit")
        return

    print("\nWriting...", flush=True)

    def _prov(pk: int, col: str, raw: str, ing: str) -> None:
        nonlocal next_prov
        cur.execute(
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name,
                source_tab, source_row, source_column, raw_value, ingested_value)
               VALUES (%s,'project',%s,%s,'google_sheet',%s,%s,%s,NULL,NULL,%s,%s)""",
            (next_prov, str(pk), col,
             _TF_FILE_ID, _TF_FILE_NAME, _TF_TAB,
             raw, ing),
        )
        next_prov += 1

    for pid, price, name in price_updates:
        cur.execute("UPDATE project SET purchase_price=%s WHERE project_id=%s", (price, pid))
        _prov(pid, "purchase_price", str(price), str(price))

    for pid, date, name in date_updates:
        cur.execute("UPDATE project SET acquisition_date=%s WHERE project_id=%s", (date, pid))
        _prov(pid, "acquisition_date", str(date), str(date))

    for pid, cls, name in cls_updates:
        cur.execute("UPDATE project SET quickbooks_class=%s WHERE project_id=%s", (cls, pid))
        _prov(pid, "quickbooks_class", cls, cls)

    conn.commit()
    n_prov = len(price_updates) + len(date_updates) + len(cls_updates)
    print(f"Committed:")
    print(f"  purchase_price updates:   {len(price_updates)}")
    print(f"  acquisition_date updates: {len(date_updates)}")
    print(f"  quickbooks_class updates: {len(cls_updates)}")
    print(f"  provenance rows:          {n_prov}")

    cur.execute("SELECT COUNT(*) FROM project WHERE purchase_price IS NOT NULL")
    print(f"\nDB: {cur.fetchone()[0]} projects with purchase_price")
    cur.execute("SELECT COUNT(*) FROM project WHERE acquisition_date IS NOT NULL")
    print(f"DB: {cur.fetchone()[0]} projects with acquisition_date")
    cur.execute("SELECT COUNT(*) FROM project WHERE quickbooks_class IS NOT NULL")
    print(f"DB: {cur.fetchone()[0]} projects with quickbooks_class")

    conn.close()


if __name__ == "__main__":
    main()
