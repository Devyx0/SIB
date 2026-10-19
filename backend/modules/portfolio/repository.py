"""Read queries for the portfolio browser. Current occupant = lease covering `today`."""
from __future__ import annotations

from datetime import date


def list_sectors(conn, sector_ids: frozenset[int] | None) -> list[dict]:
    scope = ""
    params: dict = {}
    if sector_ids is not None:
        if not sector_ids:
            return []
        scope = "WHERE s.sector_id = ANY(%(ids)s)"
        params["ids"] = list(sector_ids)
    rows = conn.execute(
        f"""
        SELECT
            s.sector_id,
            s.territoire,
            s.color_code,
            COUNT(DISTINCT b.project_id)::int AS project_count,
            COUNT(b.building_id)::int AS building_count
        FROM sector s
        LEFT JOIN building b ON b.sector_id = s.sector_id
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
