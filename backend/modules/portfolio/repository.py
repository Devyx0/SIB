"""Read queries for the portfolio browser. Current occupant = lease covering `today`."""
from __future__ import annotations

from datetime import date, timedelta

# The current lease of unit `u`: the latest one covering %(today)s.
_CURRENT_LEASE = """
    LEFT JOIN LATERAL (
        SELECT l.lease_id, l.statut, l.debut_bail, l.fin_bail, l.langue_bail
        FROM lease l
        WHERE l.unit_id = u.unit_id
          AND (l.debut_bail IS NULL OR l.debut_bail <= %(today)s)
          AND (l.fin_bail IS NULL OR l.fin_bail >= %(today)s)
        ORDER BY l.debut_bail DESC NULLS LAST, l.lease_id DESC
        LIMIT 1
    ) cl ON true
"""

# Active occupants on the current lease `cl`, lease holder first. A unit is
# occupied when occupant_count > 0. end_date is the last day occupied
# (exclusive next day): end_date = today means gone as of today.
_ACTIVE_TENANCY = (
    "(tr.end_date IS NULL OR tr.end_date > %(today)s) "
    "AND (tr.start_date IS NULL OR tr.start_date <= %(today)s)"
)

_OCCUPANTS = f"""
    LEFT JOIN LATERAL (
        SELECT
            ARRAY_AGG(
                t.nom_complet
                ORDER BY
                    CASE tr.capacite::text
                        WHEN 'named_on_lease' THEN 0
                        WHEN 'took_over' THEN 1
                        ELSE 2
                    END,
                    t.nom_complet
            ) FILTER (WHERE t.nom_complet IS NOT NULL) AS tenant_names,
            COUNT(*)::int AS occupant_count
        FROM tenancy_record tr
        JOIN tenant t ON t.tenant_id = tr.tenant_id
        WHERE tr.lease_id = cl.lease_id AND {_ACTIVE_TENANCY}
    ) occ ON true
"""


def list_sectors(conn, sector_ids: frozenset[int] | None, today: date) -> list[dict]:
    """Sectors with counts, current occupancy, and their largest projects' names."""
    scope = ""
    params: dict = {"today": today}
    if sector_ids is not None:
        if not sector_ids:
            return []
        scope = "WHERE s.sector_id = ANY(%(ids)s)"
        params["ids"] = list(sector_ids)
    rows = conn.execute(
        f"""
        WITH unit_occ AS (
            -- Occupied = the current lease has at least one tenant on it.
            SELECT
                u.unit_id,
                u.building_id,
                COALESCE(occ.occupant_count, 0) > 0 AS occupied
            FROM unit u
            {_CURRENT_LEASE}
            {_OCCUPANTS}
        )
        SELECT
            s.sector_id,
            s.territoire,
            s.color_code,
            COUNT(DISTINCT b.project_id)::int AS project_count,
            COUNT(DISTINCT b.building_id)::int AS building_count,
            COUNT(uo.unit_id)::int AS unit_count,
            COUNT(uo.unit_id) FILTER (WHERE uo.occupied)::int AS occupied_unit_count,
            COALESCE((
                SELECT ARRAY_AGG(tp.nom ORDER BY tp.n DESC, tp.nom)
                FROM (
                    SELECT COALESCE(p.nom_unique_projet, 'Projet ' || p.project_id) AS nom,
                           COUNT(*) AS n
                    FROM building pb
                    JOIN project p ON p.project_id = pb.project_id
                    WHERE pb.sector_id = s.sector_id
                    GROUP BY p.project_id, p.nom_unique_projet
                    ORDER BY n DESC, nom
                    LIMIT 3
                ) tp
            ), '{{}}') AS top_projects
        FROM sector s
        LEFT JOIN building b ON b.sector_id = s.sector_id
        LEFT JOIN unit_occ uo ON uo.building_id = b.building_id
        {scope}
        GROUP BY s.sector_id, s.territoire, s.color_code
        ORDER BY s.territoire NULLS LAST, s.sector_id
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_sector(conn, sector_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT
            s.sector_id,
            s.territoire,
            s.color_code,
            COUNT(DISTINCT b.project_id)::int AS project_count,
            COUNT(b.building_id)::int AS building_count
        FROM sector s
        LEFT JOIN building b ON b.sector_id = s.sector_id
        WHERE s.sector_id = %(id)s
        GROUP BY s.sector_id, s.territoire, s.color_code
        """,
        {"id": sector_id},
    ).fetchone()
    return dict(row) if row else None


def list_projects(conn, sector_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            p.project_id,
            p.nom_unique_projet,
            p.adresse_quickbooks,
            p.accounting_project_number,
            COUNT(b.building_id)::int AS building_count
        FROM project p
        JOIN building b ON b.project_id = p.project_id
        WHERE b.sector_id = %(sector_id)s
        GROUP BY p.project_id, p.nom_unique_projet, p.adresse_quickbooks, p.accounting_project_number
        ORDER BY p.nom_unique_projet NULLS LAST, p.project_id
        """,
        {"sector_id": sector_id},
    ).fetchall()
    return [dict(r) for r in rows]


def get_project(conn, project_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT project_id, nom_unique_projet, adresse_quickbooks, accounting_project_number
        FROM project WHERE project_id = %(id)s
        """,
        {"id": project_id},
    ).fetchone()
    return dict(row) if row else None


def list_buildings(
    conn,
    project_id: int,
    sector_ids: frozenset[int] | None,
    sector_id: int | None,
) -> list[dict]:
    conditions = ["b.project_id = %(project_id)s"]
    params: dict = {"project_id": project_id}
    if sector_ids is not None:
        if not sector_ids:
            return []
        conditions.append("b.sector_id = ANY(%(ids)s)")
        params["ids"] = list(sector_ids)
    if sector_id is not None:
        conditions.append("b.sector_id = %(sector_id)s")
        params["sector_id"] = sector_id
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""
        SELECT
            b.building_id,
            b.project_id,
            b.sector_id,
            b.adresse,
            b.ville,
            b.code_postal,
            b.web_building_name,
            b.actif_inactif,
            COUNT(u.unit_id)::int AS unit_count
        FROM building b
        LEFT JOIN unit u ON u.building_id = b.building_id
        WHERE {where}
        GROUP BY b.building_id
        ORDER BY b.adresse NULLS LAST, b.building_id
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_building(conn, building_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT
            b.building_id,
            b.project_id,
            b.sector_id,
            b.adresse,
            b.ville,
            b.code_postal,
            b.web_building_name,
            b.actif_inactif,
            b.nb_logements,
            b.nb_etages,
            b.annee_construction,
            b.latitude,
            b.longitude,
            b.geocode_status,
            s.territoire,
            p.nom_unique_projet,
            COUNT(u.unit_id)::int AS unit_count
        FROM building b
        LEFT JOIN sector s ON s.sector_id = b.sector_id
        LEFT JOIN project p ON p.project_id = b.project_id
        LEFT JOIN unit u ON u.building_id = b.building_id
        WHERE b.building_id = %(id)s
        GROUP BY b.building_id, s.territoire, p.nom_unique_projet
        """,
        {"id": building_id},
    ).fetchone()
    return dict(row) if row else None


def list_units(conn, building_id: int, today: date) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT
            u.unit_id,
            u.numero_appartement,
            u.unique_unit_number,
            u.rue,
            u.grandeur,
            cl.statut AS lease_statut,
            COALESCE(occ.tenant_names, '{{}}') AS tenant_names,
            COALESCE(occ.occupant_count, 0)::int AS occupant_count
        FROM unit u
        {_CURRENT_LEASE}
        {_OCCUPANTS}
        WHERE u.building_id = %(bid)s
        """,
        {"bid": building_id, "today": today},
    ).fetchall()
    return [dict(r) for r in rows]


def get_unit(conn, unit_id: int, today: date) -> dict | None:
    row = conn.execute(
        f"""
        SELECT
            u.unit_id,
            u.building_id,
            b.project_id,
            b.sector_id,
            u.numero_appartement,
            u.rue,
            u.grandeur,
            u.unique_unit_number,
            b.adresse AS building_adresse,
            b.web_building_name,
            p.nom_unique_projet,
            s.territoire,
            cl.lease_id,
            cl.debut_bail,
            cl.fin_bail,
            cl.statut,
            cl.langue_bail
        FROM unit u
        JOIN building b ON b.building_id = u.building_id
        LEFT JOIN project p ON p.project_id = b.project_id
        LEFT JOIN sector s ON s.sector_id = b.sector_id
        {_CURRENT_LEASE}
        WHERE u.unit_id = %(id)s
        """,
        {"id": unit_id, "today": today},
    ).fetchone()
    return dict(row) if row else None


def list_tenants(conn, lease_id: int, today: date) -> list[dict]:
    """Active tenancies on this lease (ended rows are omitted)."""
    rows = conn.execute(
        f"""
        SELECT
            tr.tenancy_id,
            t.tenant_id,
            t.nom_complet,
            t.telephone,
            t.telephone_international,
            t.courriel,
            tr.capacite::text AS capacite,
            tr.start_date,
            tr.end_date,
            tr.reason_for_change
        FROM tenancy_record tr
        JOIN tenant t ON t.tenant_id = tr.tenant_id
        WHERE tr.lease_id = %(lease_id)s AND {_ACTIVE_TENANCY}
        ORDER BY
            CASE tr.capacite::text
                WHEN 'named_on_lease' THEN 0
                WHEN 'took_over' THEN 1
                ELSE 2
            END,
            t.nom_complet
        """,
        {"lease_id": lease_id, "today": today},
    ).fetchall()
    return [dict(r) for r in rows]


def get_unit_tenant(conn, unit_id: int, tenant_id: int) -> dict | None:
    """The tenant, if they were ever on a lease of this unit or named on one of its turnovers."""
    row = conn.execute(
        """
        SELECT
            t.tenant_id,
            t.nom_complet,
            t.telephone,
            t.telephone_international,
            t.courriel,
            (
                SELECT tr.capacite::text
                FROM tenancy_record tr
                JOIN lease l ON l.lease_id = tr.lease_id
                WHERE tr.tenant_id = t.tenant_id AND l.unit_id = %(unit_id)s
                ORDER BY l.debut_bail DESC NULLS LAST, l.lease_id DESC
                LIMIT 1
            ) AS capacite
        FROM tenant t
        WHERE t.tenant_id = %(tenant_id)s
          AND (
            EXISTS (
                SELECT 1 FROM tenancy_record tr
                JOIN lease l ON l.lease_id = tr.lease_id
                WHERE tr.tenant_id = t.tenant_id AND l.unit_id = %(unit_id)s
            )
            OR EXISTS (
                SELECT 1 FROM unit_turnover ut
                WHERE ut.unit_id = %(unit_id)s
                  AND %(tenant_id)s IN (ut.incoming_tenant_id, ut.outgoing_tenant_id)
            )
          )
        """,
        {"unit_id": unit_id, "tenant_id": tenant_id},
    ).fetchone()
    return dict(row) if row else None


# A tenant's side of a turnover, for a tenant row aliased `me` with
# `me.tenant_id` and `me.name` (unaccented, lower-cased full name). Most
# turnovers predate tenant ids (only the raw names were imported), so a tenant
# also matches when their full name appears in the raw name field.
_TENANT_ROLE_SQL = """
    CASE
        WHEN ut.incoming_tenant_id = me.tenant_id THEN 'incoming'
        WHEN ut.outgoing_tenant_id = me.tenant_id THEN 'outgoing'
        WHEN me.name <> '' AND ut.incoming_tenant_id IS NULL
             AND unaccent(lower(COALESCE(ut.incoming_tenant_name_raw, ''))) LIKE '%%' || me.name || '%%'
            THEN 'incoming'
        WHEN me.name <> '' AND ut.outgoing_tenant_id IS NULL
             AND unaccent(lower(COALESCE(ut.outgoing_tenant_name_raw, ''))) LIKE '%%' || me.name || '%%'
            THEN 'outgoing'
    END
"""

_ME_SQL = "unaccent(lower(btrim(COALESCE(nom_complet, ''))))"


def tenants_with_turnover(conn, unit_id: int, tenant_ids: list[int]) -> set[int]:
    """Which of these tenants have at least one turnover on this unit."""
    if not tenant_ids:
        return set()
    rows = conn.execute(
        f"""
        SELECT me.tenant_id
        FROM (
            SELECT tenant_id, {_ME_SQL} AS name
            FROM tenant WHERE tenant_id = ANY(%(ids)s)
        ) me
        WHERE EXISTS (
            SELECT 1 FROM unit_turnover ut
            WHERE ut.unit_id = %(unit_id)s AND ({_TENANT_ROLE_SQL}) IS NOT NULL
        )
        """,
        {"unit_id": unit_id, "ids": tenant_ids},
    ).fetchall()
    return {r["tenant_id"] for r in rows}


def list_unit_turnovers(conn, unit_id: int, tenant_id: int) -> list[dict]:
    """Every turnover of the unit, newest first, with this tenant's role in each."""
    rows = conn.execute(
        f"""
        SELECT
            ut.*,
            COALESCE(ti.nom_complet, ut.incoming_tenant_name_raw) AS incoming_tenant_name,
            COALESCE(tout.nom_complet, ut.outgoing_tenant_name_raw) AS outgoing_tenant_name,
            {_TENANT_ROLE_SQL} AS tenant_role
        FROM unit_turnover ut
        CROSS JOIN (
            SELECT tenant_id, {_ME_SQL} AS name
            FROM tenant WHERE tenant_id = %(tenant_id)s
        ) me
        LEFT JOIN tenant ti ON ti.tenant_id = ut.incoming_tenant_id
        LEFT JOIN tenant tout ON tout.tenant_id = ut.outgoing_tenant_id
        WHERE ut.unit_id = %(unit_id)s
        ORDER BY
            COALESCE(ut.move_in_confirmed_date, ut.lease_start_date,
                     ut.move_out_confirmed_date, ut.lease_end_date) DESC NULLS LAST,
            ut.turnover_id DESC
        """,
        {"unit_id": unit_id, "tenant_id": tenant_id},
    ).fetchall()
    return [dict(r) for r in rows]


def list_turnover_settlements(conn, turnover_ids: list[int]) -> list[dict]:
    if not turnover_ids:
        return []
    rows = conn.execute(
        """
        SELECT turnover_id, deposit_amount_owed, deposit_received, deposit_refund_status,
               amount_owed_by_tenant, tal_dossier_open, edl_received, edl_satisfactory, notes
        FROM unit_turnover_settlement
        WHERE turnover_id = ANY(%(ids)s)
        ORDER BY settlement_id
        """,
        {"ids": turnover_ids},
    ).fetchall()
    return [dict(r) for r in rows]


def list_turnover_furniture(conn, turnover_ids: list[int]) -> list[dict]:
    if not turnover_ids:
        return []
    rows = conn.execute(
        """
        SELECT turnover_id, appliance_type, included_current, included_new
        FROM unit_turnover_furniture_item
        WHERE turnover_id = ANY(%(ids)s)
        ORDER BY furniture_item_id
        """,
        {"ids": turnover_ids},
    ).fetchall()
    return [dict(r) for r in rows]


# ── Search & filtered unit list ───────────────────────────────────────────────
#
# A search is a list of tokens; each token is a list of alternatives (the word
# itself plus FR/EN synonyms). A row matches when every token matches some part
# of its haystack — so "peinture maple" finds a paint fact on a Maple building.

def _like(alt: str) -> str:
    escaped = alt.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _tokens_sql(hay: str, tokens: list[list[str]], params: dict, prefix: str) -> str:
    """AND over tokens, OR over each token's alternatives, accent-insensitive."""
    clauses = []
    for i, alts in enumerate(tokens):
        ors = []
        for j, alt in enumerate(alts):
            key = f"{prefix}{i}_{j}"
            params[key] = _like(alt)
            ors.append(f"unaccent(lower({hay})) LIKE unaccent(lower(%({key})s))")
        clauses.append("(" + " OR ".join(ors) + ")")
    return " AND ".join(clauses) if clauses else "TRUE"


def _any_token_sql(col: str, tokens: list[list[str]], params: dict, prefix: str) -> str:
    """True when any alternative of any token appears in `col` (used for ranking)."""
    ors = []
    for i, alts in enumerate(tokens):
        for j, alt in enumerate(alts):
            key = f"{prefix}{i}_{j}"
            params[key] = _like(alt)
            ors.append(f"unaccent(lower(COALESCE({col}, ''))) LIKE unaccent(lower(%({key})s))")
    return "(" + " OR ".join(ors) + ")" if ors else "FALSE"


def _scope_sql(sector_ids: frozenset[int] | None, params: dict, col: str = "b.sector_id") -> str:
    if sector_ids is None:
        return "TRUE"
    params["scope_ids"] = list(sector_ids)
    return f"{col} = ANY(%(scope_ids)s)"


_UNIT_HAY = (
    "concat_ws(' ', u.unique_unit_number, u.numero_appartement, u.rue, u.grandeur, "
    "b.adresse, b.web_building_name, array_to_string(occ.tenant_names, ' '))"
)


def search_units(conn, tokens, sector_ids, today: date, limit: int) -> list[dict]:
    params: dict = {"today": today, "lim": limit, "words": [a[0] for a in tokens]}
    where = _tokens_sql(_UNIT_HAY, tokens, params, "t")
    rows = conn.execute(
        f"""
        SELECT
            u.unit_id,
            u.building_id,
            u.numero_appartement,
            u.unique_unit_number,
            u.rue,
            u.grandeur,
            b.adresse AS building_adresse,
            COALESCE(occ.tenant_names, '{{}}') AS tenant_names,
            COALESCE(occ.occupant_count, 0)::int AS occupant_count
        FROM unit u
        JOIN building b ON b.building_id = u.building_id
        {_CURRENT_LEASE}
        {_OCCUPANTS}
        WHERE {_scope_sql(sector_ids, params)} AND {where}
        ORDER BY
            CASE WHEN lower(u.numero_appartement) = ANY(%(words)s)
                   OR lower(u.unique_unit_number) = ANY(%(words)s) THEN 0 ELSE 1 END,
            b.adresse NULLS LAST, u.numero_appartement, u.unit_id
        LIMIT %(lim)s
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def search_buildings(conn, tokens, sector_ids, limit: int) -> list[dict]:
    params: dict = {"lim": limit}
    hay = (
        "concat_ws(' ', b.adresse, b.ville, b.code_postal, b.web_building_name, "
        "p.nom_unique_projet, s.territoire)"
    )
    where = _tokens_sql(hay, tokens, params, "t")
    rank = _any_token_sql("b.adresse", tokens, params, "r")
    rows = conn.execute(
        f"""
        SELECT
            b.building_id,
            b.project_id,
            b.sector_id,
            b.adresse,
            b.ville,
            b.web_building_name,
            p.nom_unique_projet,
            s.territoire
        FROM building b
        LEFT JOIN project p ON p.project_id = b.project_id
        LEFT JOIN sector s ON s.sector_id = b.sector_id
        WHERE {_scope_sql(sector_ids, params)} AND {where}
        ORDER BY CASE WHEN {rank} THEN 0 ELSE 1 END, b.adresse NULLS LAST, b.building_id
        LIMIT %(lim)s
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def search_projects(conn, tokens, sector_ids, limit: int) -> list[dict]:
    params: dict = {"lim": limit}
    hay = "concat_ws(' ', p.nom_unique_projet, p.adresse_quickbooks, p.accounting_project_number)"
    where = _tokens_sql(hay, tokens, params, "t")
    rows = conn.execute(
        f"""
        SELECT
            p.project_id,
            MIN(b.sector_id)::int AS sector_id,
            p.nom_unique_projet,
            p.adresse_quickbooks,
            p.accounting_project_number,
            COUNT(b.building_id)::int AS building_count
        FROM project p
        JOIN building b ON b.project_id = p.project_id
        WHERE {_scope_sql(sector_ids, params)} AND {where}
        GROUP BY p.project_id
        ORDER BY p.nom_unique_projet NULLS LAST, p.project_id
        LIMIT %(lim)s
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def search_tenants(conn, tokens, sector_ids, today: date, limit: int) -> list[dict]:
    """Current tenants only — a past tenant's unit is no longer theirs."""
    params: dict = {"today": today, "lim": limit}
    hay = "concat_ws(' ', t.nom_complet, t.telephone, t.courriel)"
    where = _tokens_sql(hay, tokens, params, "t")
    rows = conn.execute(
        f"""
        SELECT * FROM (
            SELECT DISTINCT ON (t.tenant_id)
                t.tenant_id,
                t.nom_complet,
                u.unit_id,
                u.numero_appartement,
                b.adresse AS building_adresse
            FROM unit u
            JOIN building b ON b.building_id = u.building_id
            {_CURRENT_LEASE}
            JOIN tenancy_record tr ON tr.lease_id = cl.lease_id
            JOIN tenant t ON t.tenant_id = tr.tenant_id
            WHERE {_scope_sql(sector_ids, params)} AND {_ACTIVE_TENANCY} AND {where}
            ORDER BY t.tenant_id, cl.debut_bail DESC NULLS LAST
        ) hits
        ORDER BY nom_complet NULLS LAST, tenant_id
        LIMIT %(lim)s
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def search_facts(conn, tokens, sector_ids, limit: int) -> list[dict]:
    """Fiche-technique entries and paint specs of buildings, matched with the address."""
    params: dict = {"lim": limit}
    hay = "concat_ws(' ', f.building_adresse, f.web_building_name, f.label, f.value)"
    where = _tokens_sql(hay, tokens, params, "t")
    rank = _any_token_sql("f.label", tokens, params, "r")
    rows = conn.execute(
        f"""
        WITH f AS (
            SELECT
                b.building_id, b.sector_id, b.adresse AS building_adresse, b.web_building_name,
                e.key AS label, e.value AS value, 'fiche' AS source
            FROM building b
            CROSS JOIN LATERAL jsonb_each_text(
                CASE WHEN jsonb_typeof(b.raw_fiche_technique) = 'object'
                     THEN b.raw_fiche_technique ELSE '{{}}'::jsonb END
            ) e
            WHERE e.value IS NOT NULL AND btrim(e.value) <> ''
            UNION ALL
            SELECT
                b.building_id, b.sector_id, b.adresse, b.web_building_name,
                concat_ws(' · ', 'Peinture', ps.zone, ps.surface_label),
                concat_ws(' — ', ps.product_interior, ps.product_exterior, ps.manufacturer),
                'paint_spec'
            FROM building_paint_spec ps
            JOIN building b ON b.building_id = ps.building_id
        )
        SELECT f.building_id, f.building_adresse, f.web_building_name, f.label, f.value, f.source
        FROM f
        WHERE {_scope_sql(sector_ids, params, "f.sector_id")} AND {where}
        ORDER BY CASE WHEN {rank} THEN 0 ELSE 1 END,
                 f.building_adresse NULLS LAST, f.source, f.label
        LIMIT %(lim)s
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def list_units_filtered(
    conn,
    *,
    sector_ids: frozenset[int] | None,
    today: date,
    sector_id: int | None,
    project_id: int | None,
    building_id: int | None,
    occupancy: str | None,
    grandeur: str | None,
    lease_ending_within_days: int | None,
    tokens: list[list[str]],
    limit: int,
    offset: int,
) -> dict:
    """One page of units across the portfolio, with totals for the whole filter."""
    params: dict = {"today": today, "lim": limit, "off": offset}
    # Filters that define the population; the grandeur options come from it.
    base = [_scope_sql(sector_ids, params)]
    if sector_id is not None:
        base.append("b.sector_id = %(sector_id)s")
        params["sector_id"] = sector_id
    if project_id is not None:
        base.append("b.project_id = %(project_id)s")
        params["project_id"] = project_id
    if building_id is not None:
        base.append("b.building_id = %(building_id)s")
        params["building_id"] = building_id
    if tokens:
        base.append(_tokens_sql(_UNIT_HAY, tokens, params, "t"))
    # Narrowing filters. vacant_total ignores the occupancy filter so the
    # « Vacants » chip keeps its count while another chip is selected.
    narrow = []
    if grandeur:
        narrow.append("u.grandeur = %(grandeur)s")
        params["grandeur"] = grandeur
    if lease_ending_within_days is not None:
        narrow.append("cl.fin_bail BETWEEN %(today)s AND %(lease_end_by)s")
        params["lease_end_by"] = today + timedelta(days=lease_ending_within_days)
    occ_sql = {"vacant": "occupant_count = 0", "occupied": "occupant_count > 0"}.get(occupancy or "", "TRUE")

    base_sql = " AND ".join(base)
    narrow_sql = " AND ".join(narrow) if narrow else "TRUE"
    cte = f"""
        WITH rows AS (
            SELECT
                u.unit_id,
                u.building_id,
                b.project_id,
                b.sector_id,
                u.numero_appartement,
                u.unique_unit_number,
                u.rue,
                u.grandeur,
                b.adresse AS building_adresse,
                p.nom_unique_projet,
                s.territoire,
                cl.statut AS lease_statut,
                cl.fin_bail,
                COALESCE(occ.tenant_names, '{{}}') AS tenant_names,
                COALESCE(occ.occupant_count, 0)::int AS occupant_count,
                ({narrow_sql}) AS narrowed
            FROM unit u
            JOIN building b ON b.building_id = u.building_id
            LEFT JOIN project p ON p.project_id = b.project_id
            LEFT JOIN sector s ON s.sector_id = b.sector_id
            {_CURRENT_LEASE}
            {_OCCUPANTS}
            WHERE {base_sql}
        )
    """
    totals = conn.execute(
        cte + f"""
        SELECT
            COUNT(*) FILTER (WHERE narrowed AND {occ_sql})::int AS total,
            COUNT(*) FILTER (WHERE narrowed AND occupant_count = 0)::int AS vacant_total,
            COALESCE(ARRAY_AGG(DISTINCT grandeur) FILTER (WHERE grandeur IS NOT NULL), '{{}}')
                AS grandeur_options
        FROM rows
        """,
        params,
    ).fetchone()
    items = conn.execute(
        cte + rf"""
        SELECT * FROM rows
        WHERE narrowed AND {occ_sql}
        ORDER BY
            building_adresse NULLS LAST,
            building_id,
            NULLIF(regexp_replace(COALESCE(numero_appartement, ''), '\D', '', 'g'), '')::numeric NULLS LAST,
            numero_appartement,
            unit_id
        LIMIT %(lim)s OFFSET %(off)s
        """,
        params,
    ).fetchall()
    return {
        "items": [dict(r) for r in items],
        "total": totals["total"],
        "vacant_total": totals["vacant_total"],
        "grandeur_options": sorted(totals["grandeur_options"], key=_grandeur_key),
    }


def _grandeur_key(g: str) -> tuple:
    """'3 1/2' before '4 1/2' before '10 1/2'; anything unparsable last."""
    head = g.strip().split(" ")[0]
    try:
        return (0, float(head), g)
    except ValueError:
        return (1, 0.0, g)


_TENANT_HAY = (
    "concat_ws(' ', t.nom_complet, t.telephone, t.telephone_international, t.courriel, "
    "u.unique_unit_number, u.numero_appartement, b.adresse, b.web_building_name)"
)


def list_tenants_filtered(
    conn,
    *,
    sector_ids: frozenset[int] | None,
    today: date,
    sector_id: int | None,
    project_id: int | None,
    building_id: int | None,
    unit_id: int | None,
    capacite: str | None,
    lease_ending_within_days: int | None,
    tokens: list[list[str]],
    limit: int,
    offset: int,
) -> dict:
    """One page of current occupants across the portfolio."""
    params: dict = {"today": today, "lim": limit, "off": offset}
    where = [_scope_sql(sector_ids, params)]
    if sector_id is not None:
        where.append("b.sector_id = %(sector_id)s")
        params["sector_id"] = sector_id
    if project_id is not None:
        where.append("b.project_id = %(project_id)s")
        params["project_id"] = project_id
    if building_id is not None:
        where.append("b.building_id = %(building_id)s")
        params["building_id"] = building_id
    if unit_id is not None:
        where.append("u.unit_id = %(unit_id)s")
        params["unit_id"] = unit_id
    if capacite:
        where.append("tr.capacite::text = %(capacite)s")
        params["capacite"] = capacite
    if lease_ending_within_days is not None:
        where.append("cl.fin_bail BETWEEN %(today)s AND %(lease_end_by)s")
        params["lease_end_by"] = today + timedelta(days=lease_ending_within_days)
    if tokens:
        where.append(_tokens_sql(_TENANT_HAY, tokens, params, "t"))

    where_sql = " AND ".join(where)
    cte = f"""
        WITH rows AS (
            SELECT
                t.tenant_id,
                tr.tenancy_id,
                t.nom_complet,
                t.telephone,
                t.telephone_international,
                t.courriel,
                tr.capacite::text AS capacite,
                u.unit_id,
                u.building_id,
                b.project_id,
                b.sector_id,
                u.numero_appartement,
                u.unique_unit_number,
                b.adresse AS building_adresse,
                p.nom_unique_projet,
                s.territoire,
                cl.lease_id,
                cl.statut AS lease_statut,
                cl.debut_bail,
                cl.fin_bail,
                EXISTS (
                    SELECT 1 FROM unit_turnover ut
                    WHERE ut.unit_id = u.unit_id
                      AND t.tenant_id IN (ut.incoming_tenant_id, ut.outgoing_tenant_id)
                ) AS has_turnover
            FROM unit u
            JOIN building b ON b.building_id = u.building_id
            LEFT JOIN project p ON p.project_id = b.project_id
            LEFT JOIN sector s ON s.sector_id = b.sector_id
            {_CURRENT_LEASE}
            JOIN tenancy_record tr ON tr.lease_id = cl.lease_id AND {_ACTIVE_TENANCY}
            JOIN tenant t ON t.tenant_id = tr.tenant_id
            WHERE {where_sql}
        )
    """
    totals = conn.execute(
        cte + "SELECT COUNT(*)::int AS total FROM rows",
        params,
    ).fetchone()
    items = conn.execute(
        cte + """
        SELECT * FROM rows
        ORDER BY
            lower(nom_complet) NULLS LAST,
            building_adresse NULLS LAST,
            unit_id,
            tenant_id
        LIMIT %(lim)s OFFSET %(off)s
        """,
        params,
    ).fetchall()
    return {
        "items": [dict(r) for r in items],
        "total": totals["total"],
    }
