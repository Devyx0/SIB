"""
ingest_employees.py — Schema migration + employee ingest + maintenance_request backfill.

Sources:
  - RENSEIGNEMENTS CONTACT IMPORTANTS IMMEUBLES ET EMPLOYÉS.xlsx (Employé (e) tab)
  - docs/client-ai-system/secteurs-et-equipe.md

Run:
    uv run python -m drive_pipeline.ingestion.ingest_employees          # dry run
    uv run python -m drive_pipeline.ingestion.ingest_employees --write  # write
"""
from __future__ import annotations

import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from psycopg2.extras import execute_values
from drive_pipeline.ingestion.db import get_conn

# ── Employee data ─────────────────────────────────────────────────────────────
# (initials, nom_employe, telephone, courriel, employment_type, role, sector_id, notes, source_confidence)
# sector_ids: 1=Haute-Ville 2=Levis-Est 3=Levis-Ouest 4=Quebec-Est 5=Quebec-Ouest 6=Sainte-Foy 7=Inconnu
EMPLOYEES = [
    ("ALLE", "Alain Lepire",            "418-563-4549", "alain.lepire@sibelanger.com",           "staff",              "Ouvrier",               5,    None,                                                                                             "documented"),
    ("ALTH", "Alexandre Thériault",     "581-998-1777", None,                                    "contractor_company", "Ouvrier-compagnie",      None, "Après-sinistre DAS",                                                                             "documented"),
    ("BESA", "Betim Salihu",            "418-559-2885", None,                                    "contractor_company", "Ouvrier-compagnie",      None, "Ménage / matières résiduelles",                                                                   "documented"),
    ("CALE", "Charles Antoine Lessard", "581-999-8999", "charles-antoine.lessard@sibelanger.com", "staff",              "Direction/coordination", None, None,                                                                                             "documented"),
    ("CHBE", "Charles Bergeron",        "418-318-5839", "charles.bergeron@sibelanger.com",        "staff",              "Direction/coordination", None, None,                                                                                             "documented"),
    ("CHFE", "Christophe Fernandez",    "581-459-8221", "christophe.fernandez@sibelanger.com",   "contractor_company", "Ouvrier-compagnie",      None, "Covers 2601 Tadoussac",                                                                          "documented"),
    ("CHGE", "Charles Genest",          "418-455-6316", "charles.genest@sibelanger.com",          "staff",              "Direction/coordination", None, "Rule A0: default coordinator for all cases (2026-07-12)",                                        "documented"),
    ("CHSL", "Christian St-Laurent",    "418-454-2351", None,                                    "contractor_company", "Ouvrier-compagnie",      None, "Pelouse / collectes / réno",                                                                      "documented"),
    ("DISP", "Dispatch",                "581-531-1011", "maintenance@sibelanger.com",             "unknown",            "Direction/coordination", None, "Dispatch mailbox — not a natural person",                                                         "documented"),
    ("FLNA", "Florence Nadeau",         "418-576-2784", None,                                    "contractor_company", "Ouvrier-compagnie",      None, None,                                                                                             "documented"),
    ("FRLA", "Frederic Larue",          "581-997-8052", "frederic.larue@sibelanger.com",          "staff",              "Ouvrier",               6,    None,                                                                                             "documented"),
    ("FRPI", "France Pichette",         "418-624-4334", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("JETH", "Jessie Thomassin",        "581-994-6983", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("JFME", "Jean-Frédéric Menada",    "581-985-0251", "jean-frederic.menada@sibelanger.com",    "staff",              "Ouvrier",               1,    "Rule A5: dedicated to ALL calls at 350 Ste-Foy; lives on site",                                  "documented"),
    ("JOTH", "Josée Therrien",          "418-440-5265", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("JC-S", "Sonia Grimard",           "418-208-9654", "sonia.grimard@sibelanger.com",           "staff",              "Ouvrier",               None, "Plâtre / sablage / peinture",                                                                    "documented"),
    ("KEPO", "Kevin Poulin",            "418-974-1131", "kevin.poulin@sibelanger.com",            "contractor_company", "Ouvrier-compagnie",      None, "Contremaître construction",                                                                       "documented"),
    ("KEPR", "Keith Proteau",           "581-994-0410", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("LIMO", "Linda Morissette",        "418-564-2310", None,                                    "contractor_company", "Ouvrier-compagnie",      None, "Nettoyage",                                                                                      "documented"),
    ("MACH", "Mahmoud Chachia",         "418-717-8503", None,                                    "contractor_company", "Ouvrier-compagnie",      None, "Rule A5: dedicated to ALL calls rive-sud de Québec (Lévis, Charny, etc.) + Ste-Foy",             "documented"),
    ("MABL", "Marc Blouin",             "418-930-3203", "marc.blouin@sibelanger.com",             "staff",              "Ouvrier",               None, "Déménageur / électros",                                                                          "documented"),
    ("MALA", "Marie-Claude Labbé",      "581-398-7313", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("MAMU", "Maxime Muise",            "581-888-8336", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("MAPO", "Martin Poirier",          "581-980-5262", "martin.poirier@sibelanger.com",          "staff",              "Ouvrier",               None, None,                                                                                             "documented"),
    ("MEDU", "Mélanie Duquette",        "581-307-3668", None,                                    "contractor_company", "Ouvrier-compagnie",      None, "Nettoyage",                                                                                      "documented"),
    ("MITR", "Miguel Tremblay",         "581-307-3668", None,                                    "contractor_company", "Ouvrier-compagnie",      4,    "Beauport-Charlesbourg",                                                                          "documented"),
    ("NAGA", "Nathalie Garneau Simard", "418-805-1182", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("NIRO", "Nicolas Rousseau",        "418-254-8183", "nicolas.rousseau@sibelanger.com",        "staff",              "Responsable technique",  1,    None,                                                                                             "documented"),
    ("PB",   "Pierre Boudreau",         "418-455-5475", "pierre.boudreau@sibelanger.com",         "staff",              "Ouvrier",               4,    "Beauport-Charlesbourg",                                                                          "documented"),
    ("PISI", "Pierre-Luc Simard",       "418-720-5819", "pierre-luc.simard@sibelanger.com",       "staff",              "Direction/coordination", None, None,                                                                                             "documented"),
    ("RIPE", "Richard Pelchat",         "418-572-4334", None,                                    "contractor_company", "Ouvrier-compagnie",      1,    "Building manager, 640 St-Jean",                                                                  "documented"),
    ("SAHA", "Said Hamidou",            "418-655-6213", "said.hamidou@sibelanger.com",            "staff",              "Ouvrier",               4,    "Rule A5: dedicated to ALL calls at Chamonix and Sully; initials to confirm",                     "documented"),
    ("SETO", "Serge Toffano",           "418-456-1167", "serge.toffano@sibelanger.com",           "staff",              "Direction/coordination", None, None,                                                                                             "documented"),
    ("SIDE", "Simon Dechecchi",         "367-382-6717", "simon.dechecchi@sibelanger.com",         "staff",              "Ouvrier",               5,    None,                                                                                             "documented"),
    ("SILE", "Simon Leclerc",           "418-473-1138", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("STBE", "Stephanie Beaudoin",      "418-934-6543", "stephanie.beaudoin@sibelanger.com",      "staff",              "Direction/coordination", None, "Coordonnatrice entretien bâtiments",                                                             "documented"),
    ("STLE", "Stéphane Lefebvre",       None,           None,                                    "staff",              "Ouvrier",               6,    None,                                                                                             "documented"),
    ("SV",   "Steve Voyer",             "418-802-4744", "steve.voyer@sibelanger.com",             "staff",              "Responsable technique",  None, "Ste-Foy (bleu paon) + Québec-Ouest (vert basilic)",                                             "documented"),
    ("SYBO", "Sylvie Bouchard",         "418-932-2737", None,                                    "staff",              "Ouvrier",               None, "Nettoyage",                                                                                      "documented"),
    ("VIBR", "Vincent Brouillette",     "581-305-6628", "vincent.brouillette@sibelanger.com",    "staff",              "Direction/coordination", None, "Heavy and preventive maintenance manager",                                                       "documented"),
    ("ZARO", "Zach Rousseau",           None,           None,                                    "staff",              "Ouvrier",               None, "Clés / puces",                                                                                   "documented"),
]

# Contacts file row numbers (header=1, ALLE=2 …); STLE/ZARO are md-only
_CONTACTS_ROW = {
    "ALLE": 2,  "ALTH": 3,  "BESA": 4,  "CALE": 5,  "CHBE": 6,  "CHGE": 7,
    "CHSL": 8,  "CHFE": 9,  "DISP": 10, "FLNA": 11, "FRPI": 12, "FRLA": 13,
    "JFME": 14, "JETH": 15, "JOTH": 16, "KEPR": 17, "KEPO": 18, "LIMO": 19,
    "MACH": 20, "MABL": 21, "MALA": 22, "MAMU": 23, "MAPO": 24, "MEDU": 25,
    "MITR": 26, "NAGA": 27, "NIRO": 28, "PB":   29, "PISI": 30, "RIPE": 31,
    "SAHA": 32, "SETO": 33, "SILE": 34, "SIDE": 35, "JC-S": 36, "SV":   37,
    "STBE": 38, "SYBO": 39, "VIBR": 40,
}

_SCHEMA_DDL = [
    "CREATE TYPE employment_type AS ENUM ('staff', 'contractor_company', 'unknown')",
    "CREATE TYPE source_confidence AS ENUM ('documented', 'inferred_from_calendar')",
    "ALTER TABLE employee ALTER COLUMN sector_id DROP NOT NULL",
    "ALTER TABLE employee ADD COLUMN IF NOT EXISTS initials varchar",
    "ALTER TABLE employee ADD COLUMN IF NOT EXISTS employment_type employment_type NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE employee ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true",
    "ALTER TABLE employee ADD COLUMN IF NOT EXISTS auth_user_id uuid",
    "ALTER TABLE employee ADD COLUMN IF NOT EXISTS source_confidence source_confidence",
    "ALTER TABLE employee ADD COLUMN IF NOT EXISTS notes text",
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'employee_initials_unique') THEN ALTER TABLE employee ADD CONSTRAINT employee_initials_unique UNIQUE (initials); END IF; END $$",
    "ALTER TABLE maintenance_request ADD COLUMN IF NOT EXISTS assigned_employee_id integer REFERENCES employee(employee_id)",
]


def _prov_source(initials: str) -> tuple[str, str, str | None, int | None]:
    if initials in _CONTACTS_ROW:
        return (
            "contacts_file",
            "RENSEIGNEMENTS CONTACT IMPORTANTS IMMEUBLES ET EMPLOYÉS.xlsx",
            "Employé (e)",
            _CONTACTS_ROW[initials],
        )
    return ("secteurs_et_equipe_md", "secteurs-et-equipe.md", None, None)


def run(dry_run: bool = True) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    prov_offset = cur.fetchone()[0]

    # ── Dry run report ────────────────────────────────────────────────────────
    print("\n=== TASK 1 — Schema DDL to apply ===")
    for stmt in _SCHEMA_DDL:
        print(f"  {stmt[:100]}")

    print(f"\n=== TASK 2 — Employee rows ({len(EMPLOYEES)} total) ===")
    print(f"  {'initials':<6} {'name':<26} {'type':<20} {'role':<25} {'sector_id'}")
    print(f"  {'-'*6} {'-'*26} {'-'*20} {'-'*25} {'-'*9}")
    for row in EMPLOYEES:
        init, name, _tel, _mail, etype, role, sid, _notes, _conf = row
        print(f"  {init:<6} {name:<26} {etype:<20} {role:<25} {str(sid)}")

    print(f"\n  Provenance rows: {len(EMPLOYEES)} (one per employee, on initials column)")

    # Backfill preview
    print("\n=== TASK 3 — Backfill preview (assigned_employee_code_raw → employee) ===")
    initials_set = {row[0] for row in EMPLOYEES}
    cur.execute("""
        SELECT assigned_employee_code_raw, COUNT(*) as cnt
        FROM maintenance_request
        WHERE assigned_employee_code_raw IS NOT NULL
        GROUP BY assigned_employee_code_raw
        ORDER BY cnt DESC
    """)
    raw_counts = cur.fetchall()
    matched = unmatched = 0
    for code, cnt in raw_counts:
        if code in initials_set:
            matched += cnt
        else:
            unmatched += cnt
            print(f"  UNMATCHED code={code!r} ({cnt} requests) — no employee row")
    cur.execute("SELECT COUNT(*) FROM maintenance_request")
    total = cur.fetchone()[0]
    print(f"\n  Total maintenance_request rows: {total}")
    print(f"  Will gain assigned_employee_id:  {matched}")
    print(f"  Remain unmatched:                {unmatched}")

    if dry_run:
        print(f"\nDRY RUN — pass --write to commit.")
        conn.close()
        return

    # ── Write ─────────────────────────────────────────────────────────────────
    try:
        # Task 1: schema DDL
        print("\nApplying schema DDL…")
        for stmt in _SCHEMA_DDL:
            try:
                cur.execute(stmt)
            except Exception as e:
                if "already exists" in str(e) or "does not exist" in str(e):
                    conn.rollback()
                    # re-open cursor after rollback
                    cur = conn.cursor()
                    print(f"  skip (already applied): {stmt[:60]}…")
                else:
                    raise
        conn.commit()
        cur = conn.cursor()

        # Task 2: employee rows
        print(f"\nInserting {len(EMPLOYEES)} employee rows…")
        emp_rows = []
        for idx, (init, name, tel, mail, etype, role, sid, notes, conf) in enumerate(EMPLOYEES, start=1):
            emp_rows.append((idx, init, name, tel, mail, sid, role, etype, True, conf, notes))

        execute_values(
            cur,
            """INSERT INTO employee
               (employee_id, initials, nom_employe, telephone, courriel,
                sector_id, role, employment_type, is_active, source_confidence, notes)
               VALUES %s""",
            emp_rows,
            page_size=100,
        )

        # Provenance — one row per employee on the initials column
        pnum = prov_offset
        prov = []
        for idx, (init, name, tel, mail, etype, role, sid, notes, conf) in enumerate(EMPLOYEES, start=1):
            src_type, src_file, src_tab, src_row = _prov_source(init)
            pnum += 1
            prov.append((
                pnum, "employee", idx, "initials",
                src_type, None, src_file, src_tab,
                src_row, "Initials",
                init, init, None,
            ))

        execute_values(
            cur,
            """INSERT INTO data_provenance
               (provenance_id, target_table, target_pk, target_column,
                source_type, source_drive_id, source_file_name, source_tab,
                source_row, source_column, raw_value, ingested_value, ingested_at)
               VALUES %s""",
            prov,
            page_size=100,
        )
        conn.commit()
        print(f"Committed: {len(emp_rows)} employee rows, {len(prov)} provenance rows.")

        # Task 3: backfill
        cur = conn.cursor()
        cur.execute("""
            UPDATE maintenance_request mr
            SET assigned_employee_id = e.employee_id
            FROM employee e
            WHERE mr.assigned_employee_code_raw = e.initials
              AND mr.assigned_employee_id IS NULL
        """)
        updated = cur.rowcount
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM maintenance_request WHERE assigned_employee_id IS NOT NULL")
        linked = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM maintenance_request")
        total = cur.fetchone()[0]
        print(f"\nBackfill: {updated} rows updated → {linked}/{total} maintenance_request rows now have assigned_employee_id.")

        # Report still-unmatched codes
        cur.execute("""
            SELECT assigned_employee_code_raw, COUNT(*) as cnt
            FROM maintenance_request
            WHERE assigned_employee_code_raw IS NOT NULL
              AND assigned_employee_id IS NULL
            GROUP BY assigned_employee_code_raw
            ORDER BY cnt DESC
        """)
        unmatched_rows = cur.fetchall()
        if unmatched_rows:
            print("\nCodes with no employee row (assigned_employee_id remains null):")
            for code, cnt in unmatched_rows:
                print(f"  {code!r}: {cnt} requests")

        cur.execute("SELECT COUNT(*) FROM data_provenance")
        print(f"\ndata_provenance total: {cur.fetchone()[0]}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run(dry_run="--write" not in sys.argv)
