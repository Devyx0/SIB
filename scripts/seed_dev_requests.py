"""Seed 20 [TEST] maintenance_request rows for dispatch-action development.

Guard: DB_TARGET=local only.
Idempotent: uses ON CONFLICT DO NOTHING on (external_source, external_ref).
All requests:
  - Title starts with '[TEST]' — never mistaken for real calls.
  - Assigned to technician or contractor only (coordinator/director are invalid assignees).
  - building_id is in the assigned employee's sector (scope rules satisfied).
  - status = 'triaged', so all actions are allowed.
Cleanup: python scripts/seed_dev_requests.py --cleanup
View in UI: set start_date / end_date to today ± 14 days in the filter bar.
"""
import os
import sys
from datetime import date, timedelta

import psycopg
from psycopg.rows import dict_row

DB_TARGET = os.environ.get("DB_TARGET", "local")
if DB_TARGET != "local":
    sys.exit("DB_TARGET must be 'local' — refusing to seed a non-local database")

LOCAL_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

today = date.today()

# (external_ref, raw_title, assigned_employee_id, building_id, sector_id, urgency_tier, start_offset_days)
# Employees used — all technician or contractor, each building is in their sector:
#   emp 14  Jean-Frédéric Menada  technician  sector 1  → buildings 3, 4, 14
#   emp 28  Nicolas Rousseau      technician  sector 1  → buildings 15, 16, 17
#   emp 31  Richard Pelchat       contractor  sector 1  → buildings 41, 58
#   emp 29  Pierre Boudreau       technician  sector 4  → buildings 1, 18, 24
#   emp 32  Said Hamidou          technician  sector 4  → buildings 25, 26
#   emp 26  Miguel Tremblay       contractor  sector 4  → buildings 27, 28
#   emp 1   Alain Lepire          technician  sector 5  → buildings 2, 5
#   emp 34  Simon Dechecchi       technician  sector 5  → buildings 6, 7
#   emp 11  Frederic Larue        technician  sector 6  → buildings 60, 61
#   emp 37  Stéphane Lefebvre     technician  sector 6  → buildings 62, 63
ROWS = [
    ("dev-r-001", "[TEST] Fuite d'eau salle de bain",        14, 3,  1, None,   1),
    ("dev-r-002", "[TEST] Problème chauffage",               14, 4,  1, None,   2),
    ("dev-r-003", "[TEST] Porte brisée",                     14, 14, 1, None,   3),
    ("dev-r-004", "[TEST] Infiltration eau plafond",         28, 15, 1, None,   4),
    ("dev-r-005", "[TEST] Drain bouché cuisine",             28, 16, 1, None,   5),
    ("dev-r-006", "[TEST] Serrure défectueuse",              28, 17, 1, None,   6),
    ("dev-r-007", "[TEST] Ascenseur hors service",           31, 41, 1, "Intermédiaire",  7),
    ("dev-r-008", "[TEST] Bris de glace fenêtre",            31, 58, 1, None,   8),
    ("dev-r-009", "[TEST] Urgence plomberie — eau coupée",   29, 1,  4, "URGENT",  1),
    ("dev-r-010", "[TEST] Urgence électrique court-circuit", 29, 18, 4, "URGENT",  2),
    ("dev-r-011", "[TEST] Toiture à réparer",                32, 25, 4, "Intermédiaire",  3),
    ("dev-r-012", "[TEST] Stationnement enneigé",            32, 26, 4, "Intermédiaire",  4),
    ("dev-r-013", "[TEST] Verrou portail brisé",             26, 27, 4, None,   5),
    ("dev-r-014", "[TEST] Drain extérieur bouché",           26, 28, 4, None,   6),
    ("dev-r-015", "[TEST] Fenêtre cassée balcon",             1, 2,  5, None,   7),
    ("dev-r-016", "[TEST] Balcon à réparer — garde-corps",    1, 5,  5, "URGENT",  8),
    ("dev-r-017", "[TEST] Éclairage extérieur hors service",  34, 6, 5, None,   9),
    ("dev-r-018", "[TEST] Infiltration moisissures",          11, 60, 6, "URGENT", 10),
    ("dev-r-019", "[TEST] Plancher à remplacer",              11, 61, 6, None,  11),
    ("dev-r-020", "[TEST] Réfrigérateur brisé — locataire",   37, 62, 6, "Intermédiaire", 12),
]


def seed(conn: psycopg.Connection) -> None:
    inserted = 0
    for ref, title, emp_id, bldg_id, sector_id, urgency, offset in ROWS:
        start_date = today + timedelta(days=offset)
        result = conn.execute(
            """
            INSERT INTO maintenance_request
                (status, raw_title, assigned_employee_id, building_id, sector_id,
                 urgency_tier, start_date, external_source, external_ref)
            VALUES ('triaged', %(title)s, %(emp_id)s, %(bldg_id)s, %(sector_id)s,
                    %(urgency)s, %(start_date)s, 'dev_seed', %(ref)s)
            ON CONFLICT (external_source, external_ref)
                WHERE external_source IS NOT NULL AND external_ref IS NOT NULL
            DO NOTHING
            """,
            {"title": title, "emp_id": emp_id, "bldg_id": bldg_id, "sector_id": sector_id,
             "urgency": urgency, "start_date": start_date, "ref": ref},
        )
        inserted += result.rowcount
    conn.commit()
    print(f"Inserted {inserted} new request(s) (skipped {len(ROWS) - inserted} existing).")
    print(f"View in UI: set date range to {today} – {today + timedelta(days=14)}")


def cleanup(conn: psycopg.Connection) -> None:
    # Must delete child rows before the parent to satisfy FK constraints.
    # data_provenance has no FK to maintenance_request, so it is left alone.
    jlog = conn.execute(
        "DELETE FROM decision_justification_log WHERE request_id IN "
        "(SELECT request_id FROM maintenance_request WHERE external_source = 'dev_seed')"
    ).rowcount
    flog = conn.execute(
        "DELETE FROM maintenance_followup_entry WHERE request_id IN "
        "(SELECT request_id FROM maintenance_request WHERE external_source = 'dev_seed')"
    ).rowcount
    result = conn.execute("DELETE FROM maintenance_request WHERE external_source = 'dev_seed'")
    conn.commit()
    print(f"Deleted {jlog} justification row(s), {flog} followup entry row(s), "
          f"{result.rowcount} dev_seed request(s).")


if __name__ == "__main__":
    mode = "cleanup" if "--cleanup" in sys.argv else "seed"
    with psycopg.connect(LOCAL_DSN, row_factory=dict_row) as conn:
        if mode == "cleanup":
            cleanup(conn)
        else:
            seed(conn)
