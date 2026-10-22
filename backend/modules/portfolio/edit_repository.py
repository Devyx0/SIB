"""Write queries for the portfolio: create / edit projects, buildings, units and
the building reference info (fiche technique, paint specs, documents).

Column names are never taken from user input: every write goes through the
whitelists below, which mirror the edit schemas.
"""
from __future__ import annotations

from psycopg.types.json import Jsonb

_PROJECT_COLUMNS = frozenset({"nom_unique_projet", "adresse_quickbooks", "accounting_project_number"})

_BUILDING_COLUMNS = frozenset({
    "adresse", "ville", "code_postal", "web_building_name", "actif_inactif",
    "nb_logements", "nb_etages", "annee_construction",
    "chauffage", "chauffage_details", "chauffe_eau", "systeme_incendie",
    "boite_a_cle_ext", "boite_a_cle_int", "internet", "furnished", "building_structure",
    "property_type", "ascenseur", "nb_elevateurs", "piscine", "sauna", "gym", "dogs_allowed",
})

_UNIT_COLUMNS = frozenset({"numero_appartement", "rue", "grandeur", "unique_unit_number"})

_PAINT_COLUMNS = frozenset({"zone", "surface_label", "product_interior", "product_exterior", "manufacturer"})

# table → (primary key, editable columns)
_TABLES: dict[str, tuple[str, frozenset[str]]] = {
    "project": ("project_id", _PROJECT_COLUMNS),
    "building": ("building_id", _BUILDING_COLUMNS),
    "unit": ("unit_id", _UNIT_COLUMNS),
    "building_paint_spec": ("paint_spec_id", _PAINT_COLUMNS),
}


def _checked(table: str, columns) -> tuple[str, list[str]]:
    pk, allowed = _TABLES[table]
    cols = list(columns)
    unknown = set(cols) - allowed
    if unknown:
        raise ValueError(f"not editable on {table}: {sorted(unknown)}")
    return pk, cols


def update_columns(conn, table: str, pk_value: int, changes: dict) -> None:
    if not changes:
        return
    pk, cols = _checked(table, changes)
    sets = ", ".join(f"{c} = %({c})s" for c in cols)
    conn.execute(f"UPDATE {table} SET {sets} WHERE {pk} = %(pk)s", {**changes, "pk": pk_value})


# Foreign keys a new row of each table is attached by.
_PARENTS: dict[str, frozenset[str]] = {
    "project": frozenset(),
    "building": frozenset({"project_id", "sector_id"}),
    "unit": frozenset({"building_id"}),
    "building_paint_spec": frozenset({"building_id"}),
}


def insert_row(conn, table: str, values: dict, parents: dict | None = None) -> int:
    """Insert and return the new id (identity column)."""
    parents = parents or {}
    pk, cols = _checked(table, values)
    if set(parents) - _PARENTS[table]:
        raise ValueError(f"not a parent of {table}: {sorted(set(parents) - _PARENTS[table])}")
    names = cols + list(parents)
    marks = ", ".join(f"%({c})s" for c in names)
    row = conn.execute(
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({marks}) RETURNING {pk}",
        {**values, **parents},
    ).fetchone()
    return row[pk]


# ── Locks (SELECT … FOR UPDATE) with the sector, for scope checks ─────────────

def lock_project(conn, project_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT project_id, nom_unique_projet, adresse_quickbooks, accounting_project_number,
               COALESCE((SELECT ARRAY_AGG(DISTINCT b.sector_id) FROM building b
                         WHERE b.project_id = p.project_id), '{}') AS sector_ids
        FROM project p
        WHERE project_id = %(id)s
        FOR UPDATE
        """,
        {"id": project_id},
    ).fetchone()
    return dict(row) if row else None


def lock_building(conn, building_id: int) -> dict | None:
    cols = ", ".join(sorted(_BUILDING_COLUMNS))
    row = conn.execute(
        f"""
        SELECT building_id, project_id, sector_id, raw_fiche_technique, {cols}
        FROM building
        WHERE building_id = %(id)s
        FOR UPDATE
        """,
        {"id": building_id},
    ).fetchone()
    return dict(row) if row else None


def lock_unit(conn, unit_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT u.unit_id, u.building_id, b.sector_id,
               u.numero_appartement, u.rue, u.grandeur, u.unique_unit_number
        FROM unit u
        JOIN building b ON b.building_id = u.building_id
        WHERE u.unit_id = %(id)s
        FOR UPDATE OF u
        """,
        {"id": unit_id},
    ).fetchone()
    return dict(row) if row else None


def lock_paint_spec(conn, paint_spec_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT ps.paint_spec_id, ps.building_id, b.sector_id,
               ps.zone, ps.surface_label, ps.product_interior, ps.product_exterior, ps.manufacturer
        FROM building_paint_spec ps
        JOIN building b ON b.building_id = ps.building_id
        WHERE ps.paint_spec_id = %(id)s
        FOR UPDATE OF ps
        """,
        {"id": paint_spec_id},
    ).fetchone()
    return dict(row) if row else None


def get_document(conn, document_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT d.document_id, d.building_id, b.sector_id, d.title, d.url, d.category
        FROM building_document d
        JOIN building b ON b.building_id = d.building_id
        WHERE d.document_id = %(id)s
        """,
        {"id": document_id},
    ).fetchone()
    return dict(row) if row else None


def project_exists(conn, project_id: int) -> bool:
    return conn.execute("SELECT 1 FROM project WHERE project_id = %(id)s", {"id": project_id}).fetchone() is not None


def sector_exists(conn, sector_id: int) -> bool:
    return conn.execute("SELECT 1 FROM sector WHERE sector_id = %(id)s", {"id": sector_id}).fetchone() is not None


def unique_unit_number_taken(conn, value: str, exclude_unit_id: int | None = None) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM unit
        WHERE unique_unit_number = %(v)s AND unit_id IS DISTINCT FROM %(ex)s
        """,
        {"v": value, "ex": exclude_unit_id},
    ).fetchone()
    return row is not None


# ── Fiche technique (building.raw_fiche_technique jsonb) ──────────────────────

def set_fiche_entry(conn, building_id: int, label: str, value: str | None) -> None:
    """Set one label (as a JSON string), or remove it when value is None."""
    base = ("CASE WHEN jsonb_typeof(raw_fiche_technique) = 'object' "
            "THEN raw_fiche_technique ELSE '{}'::jsonb END")
    if value is None:
        conn.execute(
            f"UPDATE building SET raw_fiche_technique = {base} - %(label)s WHERE building_id = %(id)s",
            {"label": label, "id": building_id},
        )
    else:
        conn.execute(
            f"""
            UPDATE building
            SET raw_fiche_technique = {base} || %(entry)s
            WHERE building_id = %(id)s
            """,
            {"entry": Jsonb({label: value}), "id": building_id},
        )


# ── Reads for the building page ───────────────────────────────────────────────

def list_paint_specs(conn, building_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT paint_spec_id, zone, surface_label, product_interior, product_exterior, manufacturer
        FROM building_paint_spec
        WHERE building_id = %(id)s
        ORDER BY zone NULLS LAST, paint_spec_id
        """,
        {"id": building_id},
    ).fetchall()
    return [dict(r) for r in rows]


def list_documents(conn, building_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT document_id, title, category, url
        FROM building_document
        WHERE building_id = %(id)s
        ORDER BY title NULLS LAST, document_id
        """,
        {"id": building_id},
    ).fetchall()
    return [dict(r) for r in rows]


def get_building_reference(conn, building_id: int) -> dict | None:
    """The typed reference columns and the fiche technique as text values."""
    row = conn.execute(
        """
        SELECT
            chauffage, chauffage_details, chauffe_eau, systeme_incendie,
            boite_a_cle_ext, boite_a_cle_int, internet, furnished, building_structure,
            property_type, ascenseur, nb_elevateurs, piscine, sauna, gym, dogs_allowed,
            COALESCE((
                SELECT jsonb_object_agg(e.key, e.value)
                FROM jsonb_each_text(
                    CASE WHEN jsonb_typeof(raw_fiche_technique) = 'object'
                         THEN raw_fiche_technique ELSE '{}'::jsonb END
                ) e
                WHERE e.value IS NOT NULL AND btrim(e.value) <> ''
            ), '{}'::jsonb) AS fiche
        FROM building
        WHERE building_id = %(id)s
        """,
        {"id": building_id},
    ).fetchone()
    return dict(row) if row else None


def delete_paint_spec(conn, paint_spec_id: int) -> None:
    conn.execute("DELETE FROM building_paint_spec WHERE paint_spec_id = %(id)s", {"id": paint_spec_id})


def insert_document(conn, building_id: int, title: str, url: str, category: str | None) -> int:
    row = conn.execute(
        """
        INSERT INTO building_document (building_id, title, url, category)
        VALUES (%(bid)s, %(title)s, %(url)s, %(category)s)
        RETURNING document_id
        """,
        {"bid": building_id, "title": title, "url": url, "category": category},
    ).fetchone()
    return row["document_id"]


def delete_document(conn, document_id: int) -> None:
    conn.execute("DELETE FROM building_document WHERE document_id = %(id)s", {"id": document_id})
