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

_TENANT_COLUMNS = frozenset({
    "nom_complet", "telephone", "telephone_international", "courriel",
})

_TENANCY_COLUMNS = frozenset({"capacite", "reason_for_change", "start_date", "end_date"})

_LEASE_COLUMNS = frozenset({"debut_bail", "fin_bail", "statut", "langue_bail", "unit_id"})

# table → (primary key, editable columns)
_TABLES: dict[str, tuple[str, frozenset[str]]] = {
    "project": ("project_id", _PROJECT_COLUMNS),
    "building": ("building_id", _BUILDING_COLUMNS),
    "unit": ("unit_id", _UNIT_COLUMNS),
    "building_paint_spec": ("paint_spec_id", _PAINT_COLUMNS),
    "tenant": ("tenant_id", _TENANT_COLUMNS),
    "tenancy_record": ("tenancy_id", _TENANCY_COLUMNS),
    "lease": ("lease_id", _LEASE_COLUMNS),
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

    def _set(c: str) -> str:
        if table == "tenancy_record" and c == "capacite":
            return f"{c} = %({c})s::tenancy_capacity"
        return f"{c} = %({c})s"

    sets = ", ".join(_set(c) for c in cols)
    conn.execute(f"UPDATE {table} SET {sets} WHERE {pk} = %(pk)s", {**changes, "pk": pk_value})


# Foreign keys a new row of each table is attached by.
_PARENTS: dict[str, frozenset[str]] = {
    "project": frozenset(),
    "building": frozenset({"project_id", "sector_id"}),
    "unit": frozenset({"building_id"}),
    "building_paint_spec": frozenset({"building_id"}),
    "tenant": frozenset(),
    "tenancy_record": frozenset({"lease_id", "tenant_id"}),
    "lease": frozenset({"unit_id"}),
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


def set_building_geocode(
    conn,
    building_id: int,
    *,
    latitude: float | None,
    longitude: float | None,
    status: str,
    query: str | None,
) -> None:
    """Write geocode columns (not in the portfolio edit whitelist)."""
    conn.execute(
        """
        UPDATE building
        SET latitude = %(lat)s,
            longitude = %(lon)s,
            geocode_status = %(status)s,
            geocode_query = %(query)s,
            geocoded_at = now()
        WHERE building_id = %(id)s
        """,
        {
            "id": building_id,
            "lat": latitude,
            "lon": longitude,
            "status": status,
            "query": query or None,
        },
    )


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


# ── Tenant / tenancy / lease ──────────────────────────────────────────────────

def lock_tenant(conn, tenant_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT tenant_id, nom_complet, telephone, telephone_international, courriel
        FROM tenant
        WHERE tenant_id = %(id)s
        FOR UPDATE
        """,
        {"id": tenant_id},
    ).fetchone()
    return dict(row) if row else None


def tenant_in_scope_sector(conn, tenant_id: int, sector_ids: frozenset[int] | None) -> bool:
    """True when the tenant appears on any lease of an in-scope unit."""
    params: dict = {"tid": tenant_id}
    scope = "TRUE"
    if sector_ids is not None:
        if not sector_ids:
            return False
        params["scope_ids"] = list(sector_ids)
        scope = "b.sector_id = ANY(%(scope_ids)s)"
    row = conn.execute(
        f"""
        SELECT 1
        FROM tenancy_record tr
        JOIN lease l ON l.lease_id = tr.lease_id
        JOIN unit u ON u.unit_id = l.unit_id
        JOIN building b ON b.building_id = u.building_id
        WHERE tr.tenant_id = %(tid)s AND {scope}
        LIMIT 1
        """,
        params,
    ).fetchone()
    return row is not None


def lock_tenancy(conn, tenancy_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT
            tr.tenancy_id, tr.lease_id, tr.tenant_id,
            tr.capacite::text AS capacite,
            tr.reason_for_change, tr.start_date, tr.end_date,
            l.unit_id, b.sector_id
        FROM tenancy_record tr
        JOIN lease l ON l.lease_id = tr.lease_id
        JOIN unit u ON u.unit_id = l.unit_id
        JOIN building b ON b.building_id = u.building_id
        WHERE tr.tenancy_id = %(id)s
        FOR UPDATE OF tr
        """,
        {"id": tenancy_id},
    ).fetchone()
    return dict(row) if row else None


def lock_current_lease(conn, unit_id: int, today) -> dict | None:
    """Current lease of the unit, locked; None when vacant / no covering lease."""
    row = conn.execute(
        """
        SELECT l.lease_id, l.unit_id, l.debut_bail, l.fin_bail, l.statut, l.langue_bail,
               b.sector_id
        FROM lease l
        JOIN unit u ON u.unit_id = l.unit_id
        JOIN building b ON b.building_id = u.building_id
        WHERE l.unit_id = %(uid)s
          AND (l.debut_bail IS NULL OR l.debut_bail <= %(today)s)
          AND (l.fin_bail IS NULL OR l.fin_bail >= %(today)s)
        ORDER BY l.debut_bail DESC NULLS LAST, l.lease_id DESC
        LIMIT 1
        FOR UPDATE OF l
        """,
        {"uid": unit_id, "today": today},
    ).fetchone()
    return dict(row) if row else None


def tenant_active_on_lease(conn, lease_id: int, tenant_id: int, today) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM tenancy_record tr
        WHERE tr.lease_id = %(lid)s AND tr.tenant_id = %(tid)s
          AND (tr.end_date IS NULL OR tr.end_date > %(today)s)
          AND (tr.start_date IS NULL OR tr.start_date <= %(today)s)
        LIMIT 1
        """,
        {"lid": lease_id, "tid": tenant_id, "today": today},
    ).fetchone()
    return row is not None


def _next_id(conn, table: str, pk: str) -> int:
    """Allocate an id past MAX(pk). Needed when tests insert explicit ids and
    the identity sequence lags behind."""
    row = conn.execute(f"SELECT COALESCE(MAX({pk}), 0) + 1 AS n FROM {table}").fetchone()
    return int(row["n"])


def insert_tenant(conn, values: dict) -> int:
    cols = [c for c in ("nom_complet", "telephone", "telephone_international", "courriel") if c in values]
    tenant_id = _next_id(conn, "tenant", "tenant_id")
    names = ["tenant_id", *cols]
    marks = ", ".join(f"%({c})s" for c in names)
    conn.execute(
        f"INSERT INTO tenant ({', '.join(names)}) VALUES ({marks})",
        {**values, "tenant_id": tenant_id},
    )
    return tenant_id


def insert_tenancy(
    conn,
    *,
    lease_id: int,
    tenant_id: int,
    capacite: str,
    start_date=None,
    end_date=None,
    reason_for_change: str | None = None,
) -> int:
    tenancy_id = _next_id(conn, "tenancy_record", "tenancy_id")
    conn.execute(
        """
        INSERT INTO tenancy_record (
            tenancy_id, lease_id, tenant_id, capacite, start_date, end_date, reason_for_change
        ) VALUES (
            %(tenancy_id)s, %(lease_id)s, %(tenant_id)s, %(capacite)s::tenancy_capacity,
            %(start_date)s, %(end_date)s, %(reason)s
        )
        """,
        {
            "tenancy_id": tenancy_id,
            "lease_id": lease_id,
            "tenant_id": tenant_id,
            "capacite": capacite,
            "start_date": start_date,
            "end_date": end_date,
            "reason": reason_for_change,
        },
    )
    return tenancy_id


def insert_lease(
    conn,
    *,
    unit_id: int,
    debut_bail,
    fin_bail=None,
    statut: str | None = None,
    langue_bail: str | None = None,
) -> int:
    lease_id = _next_id(conn, "lease", "lease_id")
    conn.execute(
        """
        INSERT INTO lease (lease_id, unit_id, debut_bail, fin_bail, statut, langue_bail)
        VALUES (%(lease_id)s, %(unit_id)s, %(debut)s, %(fin)s, %(statut)s, %(langue)s)
        """,
        {
            "lease_id": lease_id,
            "unit_id": unit_id,
            "debut": debut_bail,
            "fin": fin_bail,
            "statut": statut,
            "langue": langue_bail,
        },
    )
    return lease_id


def close_open_tenancies(conn, lease_id: int, end_date) -> list[dict]:
    """Set end_date on active tenancies; return previous rows for provenance."""
    rows = conn.execute(
        """
        SELECT tenancy_id, end_date, reason_for_change
        FROM tenancy_record
        WHERE lease_id = %(lid)s AND end_date IS NULL
        FOR UPDATE
        """,
        {"lid": lease_id},
    ).fetchall()
    if not rows:
        return []
    conn.execute(
        """
        UPDATE tenancy_record
        SET end_date = %(end)s
        WHERE lease_id = %(lid)s AND end_date IS NULL
        """,
        {"lid": lease_id, "end": end_date},
    )
    return [dict(r) for r in rows]
