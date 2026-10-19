"""DB access for the weather module."""
from __future__ import annotations

import json
from typing import Any, Optional


def get_request_location(conn, request_id: int) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT mr.urgency_tier::text AS urgency_tier,
               b.ville, b.municipality, b.sib_territory
        FROM maintenance_request mr
        LEFT JOIN building b ON b.building_id = mr.building_id
        WHERE mr.request_id = %s
        """,
        [request_id],
    ).fetchone()
    return dict(row) if row else None


def list_bands(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT band_id, name, temp_min_c, temp_max_c, suggested_tier,
                  is_critical, status, sort_order
           FROM weather_threshold_band ORDER BY sort_order"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_cached_snapshot(conn, location: str) -> Optional[dict]:
    """Newest snapshot for this location within the last hour (cache)."""
    row = conn.execute(
        """
        SELECT snapshot_id, location, site_code, source, source_url,
               current_temp_c, wind_chill_c, min_forecast_temp_24h_c
        FROM weather_forecast_snapshot
        WHERE location = %s AND fetched_at > now() - interval '1 hour'
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        [location],
    ).fetchone()
    return dict(row) if row else None


def insert_snapshot(conn, *, location: str, site_code: str, reading: dict) -> dict:
    row = conn.execute(
        """
        INSERT INTO weather_forecast_snapshot
            (location, site_code, source, source_url,
             current_temp_c, wind_chill_c, min_forecast_temp_24h_c, raw)
        VALUES (%(location)s, %(site_code)s, %(source)s, %(source_url)s,
                %(current)s, %(wind)s, %(min24)s, %(raw)s::jsonb)
        RETURNING snapshot_id, location, site_code, source, source_url,
                  current_temp_c, wind_chill_c, min_forecast_temp_24h_c
        """,
        {
            "location": location, "site_code": site_code,
            "source": reading.get("source", "msc_citypage"),
            "source_url": reading.get("source_url"),
            "current": reading.get("current_temp_c"),
            "wind": reading.get("wind_chill_c"),
            "min24": reading.get("min_forecast_temp_24h_c"),
            "raw": json.dumps(reading),
        },
    ).fetchone()
    return dict(row)


def insert_evaluation(
    conn, *, request_id: int, status: str, evaluated_by: int,
    snapshot_id: Optional[int] = None, location: Optional[str] = None,
    band_name: Optional[str] = None, suggested_tier: Optional[str] = None,
    min_forecast_temp_24h_c: Any = None, is_critical: bool = False,
) -> dict:
    row = conn.execute(
        """
        INSERT INTO weather_evaluation
            (request_id, snapshot_id, location, band_name, suggested_tier,
             min_forecast_temp_24h_c, is_critical, status, evaluated_by)
        VALUES (%(request_id)s, %(snapshot_id)s, %(location)s, %(band_name)s,
                %(suggested_tier)s, %(min24)s, %(is_critical)s, %(status)s, %(evaluated_by)s)
        RETURNING evaluation_id
        """,
        {
            "request_id": request_id, "snapshot_id": snapshot_id, "location": location,
            "band_name": band_name, "suggested_tier": suggested_tier,
            "min24": min_forecast_temp_24h_c, "is_critical": is_critical,
            "status": status, "evaluated_by": evaluated_by,
        },
    ).fetchone()
    return dict(row)


def get_evaluation_provenance(conn, evaluation_id: int) -> Optional[dict]:
    """Fields to embed in a decision_justification_log.after_value on accept."""
    row = conn.execute(
        """
        SELECT e.evaluation_id, e.band_name, e.min_forecast_temp_24h_c, s.source_url
        FROM weather_evaluation e
        LEFT JOIN weather_forecast_snapshot s ON s.snapshot_id = e.snapshot_id
        WHERE e.evaluation_id = %s
        """,
        [evaluation_id],
    ).fetchone()
    return dict(row) if row else None
