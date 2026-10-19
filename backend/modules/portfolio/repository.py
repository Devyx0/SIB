"""Read queries for the portfolio browser. Current occupant = lease covering `today`."""
from __future__ import annotations

from datetime import date


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
            -- Occupied = a lease covering today with at least one tenant on it.
            SELECT
                u.unit_id,
                u.building_id,
                EXISTS (
                    SELECT 1
                    FROM lease l
                    JOIN tenancy_record tr ON tr.lease_id = l.lease_id
                    WHERE l.unit_id = u.unit_id
                      AND (l.debut_bail IS NULL OR l.debut_bail <= %(today)s)
                      AND (l.fin_bail IS NULL OR l.fin_bail >= %(today)s)
                ) AS occupied
            FROM unit u
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
        """
        SELECT
            u.unit_id,
            u.numero_appartement,
            u.rue,
            u.grandeur,
            cl.statut AS lease_statut,
            occ.tenant_name,
            COALESCE(occ.occupant_count, 0)::int AS occupant_count
        FROM unit u
        LEFT JOIN LATERAL (
            SELECT l.lease_id, l.statut
            FROM lease l
            WHERE l.unit_id = u.unit_id
              AND (l.debut_bail IS NULL OR l.debut_bail <= %(today)s)
              AND (l.fin_bail IS NULL OR l.fin_bail >= %(today)s)
            ORDER BY l.debut_bail DESC NULLS LAST, l.lease_id DESC
            LIMIT 1
        ) cl ON true
        LEFT JOIN LATERAL (
            SELECT
                (ARRAY_AGG(
                    t.nom_complet
                    ORDER BY
                        CASE tr.capacite::text
                            WHEN 'named_on_lease' THEN 0
                            WHEN 'took_over' THEN 1
                            ELSE 2
                        END,
                        t.nom_complet
                ))[1] AS tenant_name,
                COUNT(*)::int AS occupant_count
            FROM tenancy_record tr
            JOIN tenant t ON t.tenant_id = tr.tenant_id
            WHERE tr.lease_id = cl.lease_id
        ) occ ON true
        WHERE u.building_id = %(bid)s
        """,
        {"bid": building_id, "today": today},
    ).fetchall()
    return [dict(r) for r in rows]


def get_unit(conn, unit_id: int, today: date) -> dict | None:
    row = conn.execute(
        """
        SELECT
            u.unit_id,
            u.building_id,
            b.project_id,
            b.sector_id,
            u.numero_appartement,
            u.rue,
            u.grandeur,
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
        LEFT JOIN LATERAL (
            SELECT l.lease_id, l.debut_bail, l.fin_bail, l.statut, l.langue_bail
            FROM lease l
            WHERE l.unit_id = u.unit_id
              AND (l.debut_bail IS NULL OR l.debut_bail <= %(today)s)
              AND (l.fin_bail IS NULL OR l.fin_bail >= %(today)s)
            ORDER BY l.debut_bail DESC NULLS LAST, l.lease_id DESC
            LIMIT 1
        ) cl ON true
        WHERE u.unit_id = %(id)s
        """,
        {"id": unit_id, "today": today},
    ).fetchone()
    return dict(row) if row else None


def list_tenants(conn, lease_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            t.tenant_id,
            t.nom_complet,
            t.telephone,
            t.telephone_international,
            t.courriel,
            tr.capacite::text AS capacite
        FROM tenancy_record tr
        JOIN tenant t ON t.tenant_id = tr.tenant_id
        WHERE tr.lease_id = %(lease_id)s
        ORDER BY
            CASE tr.capacite::text
                WHEN 'named_on_lease' THEN 0
                WHEN 'took_over' THEN 1
                ELSE 2
            END,
            t.nom_complet
        """,
        {"lease_id": lease_id},
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
