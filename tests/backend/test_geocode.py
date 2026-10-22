"""Unit tests for Nominatim address geocoding (no live HTTP)."""
from __future__ import annotations

import httpx
import pytest

from backend.modules.portfolio.geocode import build_query, geocode_address, normalize_street


def test_normalize_street_collapses_sib_labels():
    assert normalize_street("405-415 41e Rue Ouest / 4105 Gros-Pin") == "405 41e Rue Ouest"
    assert normalize_street("580 Grande Allee / 1185-1195 Brown") == "580 Grande Allee"
    assert normalize_street("1175 Chamonix (1 a 26)") == "1175 Chamonix"
    assert normalize_street("2 a 36 Archer") == "2 Archer"
    assert normalize_street("84-86-88 Carmichael") == "84 Carmichael"
    assert normalize_street("786-796 Abraham") == "786 Abraham"
    assert normalize_street("1580 Périgord") == "1580 Périgord"
    assert normalize_street("Terrain Chemin Belair") == "Chemin Belair"


def test_build_query_skips_blanks_and_normalizes():
    assert build_query(None) is None
    assert build_query("  ") is None
    assert build_query("786-796 Abraham", "Québec") == (
        "786 Abraham, Québec, Québec, Canada"
    )
    assert build_query("1580 Périgord", "Québec", "G1E 6J5") == (
        "1580 Périgord, Québec, Québec, Canada"
    )


def _client(payload: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_geocode_ok():
    hits = [{"lat": "46.829", "lon": "-71.254", "display_name": "Québec, Canada"}]
    r = geocode_address("1 rue Test", "Québec", client=_client(hits), throttle=False)
    assert r.status == "ok"
    assert r.latitude == pytest.approx(46.829)
    assert r.longitude == pytest.approx(-71.254)
    assert "Québec, Canada" in r.query


def test_geocode_normalized_range_still_ok():
    hits = [{"lat": "46.81", "lon": "-71.22", "display_name": "Abraham, Québec"}]
    r = geocode_address("786-796 Abraham", "Québec", client=_client(hits), throttle=False)
    assert r.status == "ok"
    assert "786 Abraham" in r.query
    assert r.note == "normalized_query"


def test_geocode_no_results():
    r = geocode_address("nowhere", client=_client([]), throttle=False)
    assert r.status == "failed"
    assert r.latitude is None
    assert r.note == "no_results"


def test_geocode_outside_metro_rejected_no_coords():
    hits = [{"lat": "43.65", "lon": "-79.38", "display_name": "Toronto, ON"}]
    r = geocode_address("1 King St", client=_client(hits), throttle=False)
    assert r.status == "failed"
    assert r.latitude is None
    assert r.note == "outside_metro"


def test_geocode_prefers_metro_hit_among_ambiguous():
    hits = [
        {"lat": "45.50", "lon": "-73.56", "display_name": "Montréal"},
        {"lat": "46.80", "lon": "-71.20", "display_name": "Québec"},
    ]
    r = geocode_address("Ambiguous", client=_client(hits), throttle=False)
    assert r.status == "ok"
    assert r.latitude == pytest.approx(46.80)
    assert r.longitude == pytest.approx(-71.20)


def test_geocode_blank_skipped():
    r = geocode_address(None, client=_client([]), throttle=False)
    assert r.status == "skipped"
    assert r.note == "blank_address"


def test_set_building_geocode_writes_columns(db_conn):
    """Repo helper updates geocode columns outside the portfolio edit whitelist."""
    from backend.modules.portfolio import edit_repository as repo

    sector = db_conn.execute(
        "INSERT INTO sector (territoire) VALUES ('Geo') RETURNING sector_id"
    ).fetchone()
    project = db_conn.execute(
        "INSERT INTO project (nom_unique_projet) VALUES ('Geo Proj') RETURNING project_id"
    ).fetchone()
    building = db_conn.execute(
        """
        INSERT INTO building (project_id, sector_id, adresse)
        VALUES (%(p)s, %(s)s, '12 Test')
        RETURNING building_id
        """,
        {"p": project["project_id"], "s": sector["sector_id"]},
    ).fetchone()
    bid = building["building_id"]

    repo.set_building_geocode(
        db_conn, bid,
        latitude=46.8, longitude=-71.2, status="ok", query="12 Test, Québec, Canada",
    )
    row = db_conn.execute(
        "SELECT latitude, longitude, geocode_status, geocode_query FROM building WHERE building_id = %s",
        (bid,),
    ).fetchone()
    assert row["geocode_status"] == "ok"
    assert float(row["latitude"]) == pytest.approx(46.8)
    assert float(row["longitude"]) == pytest.approx(-71.2)
    assert row["geocode_query"] == "12 Test, Québec, Canada"
