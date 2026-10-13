"""
ingest_building_paint_spec.py — Dry-run and write ingestion of building_paint_spec
from Paint_Chart_EN.xlsx.

Run:
    uv run python -m drive_pipeline.ingestion.ingest_building_paint_spec          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_building_paint_spec --write  # write
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import openpyxl
from psycopg2.extras import execute_values

from drive_pipeline.ingestion.db import get_conn

_PAINT_PATH = ROOT / "work/dryrun_maintenance/Paint_Chart_EN.xlsx"
_SOURCE_FILE = "Paint_Chart_EN.xlsx"

# Tab name → list of building_ids that share this paint spec
_TAB_BUILDINGS: dict[str, list[int]] = {
    "CSL":               [64],               # 2829 Chemin St-Louis
    "874 AV DESSANE":    [86],               # 874 Dessane
    "GALEARMONTH":       [101, 118],         # 410-420 Grande-Allee + 435-445 Learmonth
    "640 ST-JEAN":       [128],              # 636-640-646 St-Jean
    "1035 PIE-XII":      [133],              # 1035 Pie-XII
    "CLARIDGE":          [117],              # 200-220 Grande Allee Est
    "GINGRAS":           [95, 96, 97, 98, 99, 100],  # 621-739 Gingras (6 buildings)
    "STC":               [91, 92, 93, 94],   # OSEN: 1017 Duchesneau + 3140/3146/3150 France-Prime
    "CHANOINE-MOREL":    [41],               # 1320 Chanoine-Morel
    "315 ST-JEAN":       [107],              # 315-317 St-Jean
    "ÉVANGÉLINE":        [89],               # Evangeline portion of bldg 89
    "LANGEVIN":          [108],              # 51 Langevin
    "ÉPINETTES":         [87, 88],           # 53-55 + 65-69 Epinettes
    "18 DEMERS":         [],                 # "18 RUE DEMERS" — not in DB, skip
    "DES ROSES":         [141, 142, 143, 144],  # 4298-4420 Roses
    "MGR-GOSSELIN":      [89],               # Mgr-Gosselin portion of bldg 89
    "ST-AUGUSTIN":       [3],               # 690-692 Saint-Augustin
    "CLAUDE-MARTIN":     [65, 66],           # 480 + 530 Claude-Martin
    "125135 DES CÈDRES": [84, 85],           # 125 + 135 Des Cedres
}

# STC tab: civic number → building_ids (for per-sub-group zone routing)
_STC_CIVIC_BIDS: dict[str, list[int]] = {
    "1017": [91],
    "3140": [92],
    "3146": [93],
    "3150": [94],
}

# Keywords that identify real zone headers (vs building-label rows)
_ZONE_RE = re.compile(
    r"LOGEMENT|COMMON|AIRS?\s*COMMUN|EXTERIEUR|EXTERIOR|CAGE|STAIRWELL|GYM|BUREAU|"
    r"LOCAL|BIKE|LOCKER|BUANDERIE|LAUNDRY|ASCENSEUR|STATIONNEMENT|PARKING|"
    r"SOUS.TERRAIN|UNDERGROUND|ROOFTOP|TERRACE|TERRASSE|BASEMENT|TOILETTE|BATHROOM|"
    r"PISCINE|POOL|LIGNAGE|ENTRANCE|MAIN|(?<!\w)SS(?!\w)|ESCALIER|AIRE",
    re.IGNORECASE | re.UNICODE,
)

_CIVIC_RE = re.compile(r"\b(\d{4})\b")


def _is_header(row: tuple) -> bool:
    return any(v and "PRODUITS" in str(v).upper() for v in row[1:])


def _is_zone_pattern(row: tuple) -> bool:
    return (
        row[0] is not None
        and str(row[0]).strip() != ""
        and all(v is None for v in row[1:4])
    )


def _is_data_row(row: tuple) -> bool:
    return (len(row) > 1 and row[1] is not None) or (len(row) > 2 and row[2] is not None)


def _stc_bids_from_text(text: str, fallback: list[int]) -> list[int]:
    civics = _CIVIC_RE.findall(text)
    bids: list[int] = []
    for c in civics:
        bids.extend(_STC_CIVIC_BIDS.get(c, []))
    return bids if bids else fallback


def _parse_tab(ws, tab_name: str) -> list[tuple]:
    """
    Returns list of:
        (excel_row, building_id, zone, surface_label,
         product_interior, product_exterior, manufacturer)
    """
    all_bids = _TAB_BUILDINGS.get(tab_name, [])
    if not all_bids:
        return []

    is_stc = tab_name == "STC"
    rows = list(ws.iter_rows(values_only=True))
    records: list[tuple] = []
    current_zone: str | None = None
    current_bids = all_bids

    i = 0
    while i < len(rows):
        row = rows[i]
        excel_row = i + 1

        if _is_header(row):
            i += 1
            continue

        if not any(v is not None for v in row):
            i += 1
            continue

        if _is_zone_pattern(row):
            zone_text = str(row[0]).strip()

            if not _ZONE_RE.search(zone_text):
                # Building label row — not a real zone, skip
                i += 1
                continue

            # Look ahead past empty rows for a potential sub-specifier / sub-zone row
            j = i + 1
            while j < len(rows) and not any(v is not None for v in rows[j]):
                j += 1
            if j < len(rows) and _is_zone_pattern(rows[j]):
                sub_text = str(rows[j][0]).strip()
                zone_text = f"{zone_text} {sub_text}"
                i = j + 1  # consumed both rows
            else:
                i += 1

            current_zone = zone_text
            current_bids = _stc_bids_from_text(zone_text, all_bids) if is_stc else all_bids
            continue

        if _is_data_row(row):
            surface_label = str(row[0]).strip() if row[0] else None
            product_int   = str(row[1]).strip() if len(row) > 1 and row[1] else None
            product_ext   = str(row[2]).strip() if len(row) > 2 and row[2] else None
            manufacturer  = str(row[3]).strip() if len(row) > 3 and row[3] else None
            for bid in current_bids:
                records.append((excel_row, bid, current_zone, surface_label,
                                product_int, product_ext, manufacturer))

        i += 1

    return records


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(MAX(paint_spec_id), 0) FROM building_paint_spec")
    next_id = cur.fetchone()[0] + 1

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]

    wb = openpyxl.load_workbook(str(_PAINT_PATH), read_only=True, data_only=True)

    # (excel_row, building_id, zone, surface_label, prod_int, prod_ext, manufacturer, tab_name)
    all_records: list[tuple] = []
    skipped_tabs = []

    for tab_name, bids in _TAB_BUILDINGS.items():
        if not bids:
            skipped_tabs.append(tab_name)
            continue
        ws = wb[tab_name]
        for rec in _parse_tab(ws, tab_name):
            all_records.append(rec + (tab_name,))

    wb.close()

    print(f"\n=== building_paint_spec dry run ===")
    print(f"Skipped tabs (no building_id in DB): {skipped_tabs}")
    print(f"Total paint_spec rows planned: {len(all_records)}")

    tab_counts = Counter(r[7] for r in all_records)
    for tab in _TAB_BUILDINGS:
        if tab in tab_counts:
            bids = _TAB_BUILDINGS[tab]
            print(f"  {tab}: {tab_counts[tab]} rows → buildings {bids}")

    # Sample first 5 records
    print("\nSample records (first 5):")
    for rec in all_records[:5]:
        _, bid, zone, surface, pi, pe, mfr, tab = rec
        print(f"  building_id={bid} zone={zone!r} surface={surface!r} int={pi!r} ext={pe!r} mfr={mfr!r}")

    if dry_run:
        print(f"\nDRY RUN — {len(all_records)} building_paint_spec rows planned. Pass --write to commit.")
        conn.close()
        return

    print(f"\nWriting {len(all_records)} building_paint_spec rows…")
    try:
        rows_to_insert = [
            (next_id + idx, building_id, zone, surface_label, product_int, product_ext, manufacturer)
            for idx, (excel_row, building_id, zone, surface_label, product_int, product_ext, manufacturer, tab_name)
            in enumerate(all_records)
        ]

        prov = []
        pnum = prov_offset
        for idx, (excel_row, building_id, zone, surface_label, product_int, product_ext, manufacturer, tab_name) in enumerate(all_records):
            pid = next_id + idx
            for col_name, raw_val in [
                ("zone", zone),
                ("surface_label", surface_label),
                ("product_interior", product_int),
                ("product_exterior", product_ext),
                ("manufacturer", manufacturer),
            ]:
                if raw_val is not None:
                    pnum += 1
                    prov.append((pnum, "building_paint_spec", pid, col_name,
                                 "spreadsheet", None, _SOURCE_FILE, tab_name,
                                 excel_row, col_name, raw_val, raw_val, None))

        execute_values(
            cur,
            """INSERT INTO building_paint_spec
               (paint_spec_id, building_id, zone, surface_label, product_interior, product_exterior, manufacturer)
               VALUES %s""",
            rows_to_insert,
            page_size=2000,
        )

        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov,
            page_size=5000,
        )

        conn.commit()
        print(f"Committed: {len(all_records)} building_paint_spec, {len(prov)} provenance rows.")

        cur.execute("SELECT COUNT(*) FROM building_paint_spec")
        print(f"building_paint_spec total: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM data_provenance")
        print(f"data_provenance total: {cur.fetchone()[0]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
