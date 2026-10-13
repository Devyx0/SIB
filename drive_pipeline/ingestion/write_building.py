"""
write_building.py — Real Supabase write: sector → project → building → data_provenance.

Run only after the dry run has been reviewed and approved:
    uv run python -m drive_pipeline.ingestion.write_building
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from drive_pipeline.table_fondamentale.table_fondamentale import TABLE_FONDAMENTALE
from drive_pipeline.ingestion.ingest_building import run as _ingest_run
from drive_pipeline.ingestion.db import get_conn
from drive_pipeline.ingestion.provenance import log_provenance, flush

TF_FILE = "table_fondamentale.py"

# ── Sector helpers ────────────────────────────────────────────────────────────

def _build_sector_ids() -> dict[str, int]:
    """Return {territory: sector_id}, sorted alphabetically. 'Inconnu' appended last."""
    territories = sorted({
        (r.get("sib_territory") or "").strip()
        for r in TABLE_FONDAMENTALE
        if (r.get("sib_territory") or "").strip()
    })
    result = {t: i for i, t in enumerate(territories, 1)}
    result["Inconnu"] = len(result) + 1  # fallback for buildings missing a territory
    return result


def _insert_sectors(cur, sector_ids: dict[str, int]) -> list[dict]:
    for territoire, sid in sorted(sector_ids.items(), key=lambda x: x[1]):
        cur.execute(
            "INSERT INTO sector (sector_id, territoire) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (sid, territoire),
        )
        log_provenance(
            target_table="sector", target_pk=sid, target_column="territoire",
            source_type="table_fondamentale", source_drive_id=None,
            source_file_name=TF_FILE, source_tab=None, source_row=None,
            source_column="sib_territory", raw_value=territoire, ingested_value=territoire,
        )
    return flush()


# ── Project helpers ───────────────────────────────────────────────────────────

def _build_projects() -> dict[str, dict]:
    """Return {project_name: {project_id, nom_unique_projet, adresse_quickbooks}}, sorted by name."""
    seen: dict[str, str] = {}  # name → qb_address (first occurrence wins)
    for row in TABLE_FONDAMENTALE:
        name = (row.get("unique_project_name") or "").strip()
        addr = (row.get("quickbooks_project_address") or "").strip()
        if name and name not in seen:
            seen[name] = addr
    return {
        name: {"project_id": pid, "nom_unique_projet": name, "adresse_quickbooks": addr or None}
        for pid, (name, addr) in enumerate(sorted(seen.items()), 1)
    }


def _insert_projects(cur, projects: dict[str, dict]) -> list[dict]:
    for p in sorted(projects.values(), key=lambda x: x["project_id"]):
        cur.execute(
            "INSERT INTO project (project_id, nom_unique_projet, adresse_quickbooks) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (p["project_id"], p["nom_unique_projet"], p["adresse_quickbooks"]),
        )
        for col, val, src_col in [
            ("nom_unique_projet",  p["nom_unique_projet"],  "unique_project_name"),
            ("adresse_quickbooks", p["adresse_quickbooks"], "quickbooks_project_address"),
        ]:
            if val:
                log_provenance(
                    target_table="project", target_pk=p["project_id"], target_column=col,
                    source_type="table_fondamentale", source_drive_id=None,
                    source_file_name=TF_FILE, source_tab=None, source_row=None,
                    source_column=src_col, raw_value=val, ingested_value=val,
                )
    return flush()


# ── Building insert ───────────────────────────────────────────────────────────

# varchar columns in DB schema that ingest_building produces as Python bools
_STR_BOOL_COLS = {"systeme_incendie", "boite_a_cle_ext", "boite_a_cle_int"}

_BLDG_DB_COLS = [
    "building_id", "project_id", "sector_id",
    "adresse", "ville",
    "annee_construction", "nb_etages", "nb_logements",
    "ascenseur", "piscine", "sauna", "gym",
    "chauffage", "systeme_incendie", "boite_a_cle_ext", "boite_a_cle_int",
    "raw_fiche_technique",
    "sib_territory", "furnished", "building_structure",
    "nb_elevateurs", "num_service_elevators", "internet",
    "terrasse_commune", "num_bbqs", "coworking_space", "reception_loft",
    "chauffage_details", "chauffe_eau", "individual_heat_pumps", "heat_pump_details",
]

_SQL_BLDG = (
    f"INSERT INTO building ({', '.join(_BLDG_DB_COLS)}) "
    f"VALUES ({', '.join(['%s'] * len(_BLDG_DB_COLS))}) ON CONFLICT DO NOTHING"
)


def _bldg_vals(merged: dict, project_id: int | None, sector_id: int) -> tuple:
    out = []
    for col in _BLDG_DB_COLS:
        if col == "project_id":
            out.append(project_id)
        elif col == "sector_id":
            out.append(sector_id)
        elif col == "raw_fiche_technique":
            ft = merged.get("raw_fiche_technique")
            out.append(json.dumps(ft) if ft else None)
        elif col in _STR_BOOL_COLS:
            v = merged.get(col)
            out.append("yes" if v is True else ("no" if v is False else (str(v) if v is not None else None)))
        else:
            out.append(merged.get(col))
    return tuple(out)


def _insert_buildings(cur, results: list[dict], projects: dict[str, dict], sector_ids: dict[str, int]) -> None:
    inconnu_sid = sector_ids["Inconnu"]
    for merged in results:
        proj_name = (merged.get("unique_project_name") or "").strip()
        territory = (merged.get("sib_territory") or "").strip()
        proj = projects.get(proj_name)
        project_id = proj["project_id"] if proj else None
        sector_id = sector_ids.get(territory) or inconnu_sid
        cur.execute(_SQL_BLDG, _bldg_vals(merged, project_id, sector_id))


# ── Provenance insert ─────────────────────────────────────────────────────────

_SQL_PROV = """
    INSERT INTO data_provenance
        (provenance_id, target_table, target_pk, target_column,
         source_type, source_drive_id, source_file_name, source_tab,
         source_row, source_column, raw_value, ingested_value, ingested_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT DO NOTHING
"""

# Columns that don't exist on building — moved to project table, skipped from building provenance
_SKIP_BLDG_COLS = {"unique_project_name", "quickbooks_address"}


def _insert_provenance(cur, all_prov: list[dict]) -> int:
    """Bulk insert all provenance rows. Returns count written."""
    rows = [
        r for r in all_prov
        if not (r["target_table"] == "building" and r["target_column"] in _SKIP_BLDG_COLS)
    ]
    for pid, row in enumerate(rows, 1):
        cur.execute(_SQL_PROV, (
            pid,
            row["target_table"], row["target_pk"], row["target_column"],
            row["source_type"], row["source_drive_id"], row["source_file_name"],
            row["source_tab"], row["source_row"], row["source_column"],
            row["raw_value"], row["ingested_value"],
        ))
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def write_all() -> None:
    print("=== Building write — fetching from Google Drive (may take ~3 min) ===")
    results, bldg_prov = _ingest_run(verbose=False)
    print(f"Ingestion complete: {len(results)} buildings, {len(bldg_prov)} raw building provenance rows.")

    sector_ids = _build_sector_ids()
    projects   = _build_projects()
    print(f"Seeding {len(sector_ids)} sectors and {len(projects)} projects.")

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        sec_prov  = _insert_sectors(cur, sector_ids)
        proj_prov = _insert_projects(cur, projects)
        _insert_buildings(cur, results, projects, sector_ids)

        all_prov = sec_prov + proj_prov + bldg_prov
        n_prov = _insert_provenance(cur, all_prov)

        conn.commit()
        print(f"Committed: {len(sector_ids)} sectors, {len(projects)} projects, "
              f"{len(results)} buildings, {n_prov} provenance rows.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # ── Post-write verification ────────────────────────────────────────────────
    print("\n=== Post-write verification (live Supabase) ===")
    conn = get_conn()
    cur = conn.cursor()

    for tbl in ("sector", "project", "building", "data_provenance"):
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        n = cur.fetchone()[0]
        print(f"  {tbl:<20} {n} rows")

    # Spot-check: 2 ascenseur-corrected buildings
    print("\n  Ascenseur overrides (building_id 150, 152):")
    cur.execute("SELECT building_id, adresse, ascenseur FROM building WHERE building_id IN (150, 152) ORDER BY building_id")
    for r in cur.fetchall():
        print(f"    building_id={r[0]}  {r[1]!r}  ascenseur={r[2]}")

    # Spot-check: 3 annee_construction discrepancy buildings
    print("\n  Year-discrepancy sample (building_id 13, 18, 60):")
    cur.execute("SELECT building_id, adresse, annee_construction FROM building WHERE building_id IN (13, 18, 60) ORDER BY building_id")
    for r in cur.fetchall():
        print(f"    building_id={r[0]}  {r[1]!r}  year={r[2]!r}")

    # Spot-check: provenance for building 150 ascenseur (should show 2 rows)
    print("\n  Provenance for building_id=150 col=ascenseur:")
    cur.execute("""
        SELECT source_type, raw_value, ingested_value
        FROM data_provenance
        WHERE target_table='building' AND target_pk=150 AND target_column='ascenseur'
        ORDER BY provenance_id
    """)
    for r in cur.fetchall():
        print(f"    source={r[0]!r}  raw={r[1]!r}  ingested={r[2]!r}")

    # Spot-check: provenance for building 13 annee_construction (should show 2 rows)
    print("\n  Provenance for building_id=13 col=annee_construction:")
    cur.execute("""
        SELECT source_type, raw_value, ingested_value
        FROM data_provenance
        WHERE target_table='building' AND target_pk=13 AND target_column='annee_construction'
        ORDER BY provenance_id
    """)
    for r in cur.fetchall():
        print(f"    source={r[0]!r}  raw={r[1]!r}  ingested={r[2]!r}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    write_all()
