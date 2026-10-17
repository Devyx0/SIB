"""Tests for GET /api/v1/requests and /api/v1/lookup endpoints."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.core.db import get_db_conn
from backend.core.security import CurrentUser, get_current_user
from backend.main import create_app

# Sept 2026 data range (calendar data stops Sept 25)
_START = "2026-09-01"
_END   = "2026-09-25"
_BASE  = f"start_date={_START}&end_date={_END}"

# Request 1909: building in sector 6, assigned to tech 24, has caller_name/phone.
# Used for PII and scope assertions.
_REQ_WITH_PII       = 1909
_TECH_ASSIGNED      = 24   # directly assigned to _REQ_WITH_PII → sees PII
_TECH_SECTOR        = 11   # sector 6, NOT assigned → sees request but PII nulled
_TECH_OUT           = 14   # sector 1, not assigned → 404
_COORD_EMP          = 4
_DIR_EMP            = 5
_CONTRACTOR_EMP     = 20   # Mahmoud Chachia
_REQ_CONTRACTOR     = None  # resolved dynamically — see fixture below
_REQ_WITH_LOG       = 1798  # has 2+ followup entries
_REQ_WITH_OCCUPANTS = 1445  # sector 6, assigned to tech 41, has occupants_raw
_TECH_ASSIGNED_1445 = 41   # directly assigned to _REQ_WITH_OCCUPANTS


def _user(employee_id: int, *roles: str) -> CurrentUser:
    return CurrentUser(employee_id=employee_id, roles=frozenset(roles))


@pytest.fixture
def ac(app, db_conn):
    """Return a factory: ac(user) → TestClient with that user injected."""
    from backend.core.security import get_current_user

    def _factory(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_db_conn] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield _factory
    app.dependency_overrides.clear()


# ── Date-range validation ──────────────────────────────────────────────────────

def test_list_missing_start_date_is_422(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?end_date={_END}")
    assert r.status_code == 422


def test_list_missing_end_date_is_422(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?start_date={_START}")
    assert r.status_code == 422


def test_list_date_range_over_31_days_is_422(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    far_end = date(2026, 9, 1) + timedelta(days=32)
    r = c.get(f"/api/v1/requests?start_date=2026-09-01&end_date={far_end}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_list_date_range_31_days_is_ok(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    ok_end = date(2026, 9, 1) + timedelta(days=31)
    r = c.get(f"/api/v1/requests?start_date=2026-09-01&end_date={ok_end}")
    assert r.status_code == 200


# ── Basic list shape ───────────────────────────────────────────────────────────

def test_list_returns_data_and_total(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}")
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and "items" in body
    assert body["total"] > 0
    assert len(body["items"]) > 0


def test_list_no_pii_in_list_response(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=20")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert "caller_name"  not in item or item.get("caller_name")  is None
        assert "caller_phone" not in item or item.get("caller_phone") is None
        assert "caller_email" not in item or item.get("caller_email") is None


def test_list_source_calendar_label_populated(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&source_calendar=main&limit=1")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["source_calendar"] == "main"
    assert item["source_calendar_label"] == "Calendrier principal"


def test_list_null_fields_present(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=1")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert "estimated_cost"      in item
    assert "next_follow_up_date" in item
    assert "next_steps"          in item
    # existing rows have no data yet — all NULL
    assert item["estimated_cost"]      is None
    assert item["next_follow_up_date"] is None
    assert item["next_steps"]          is None


# ── Filters ────────────────────────────────────────────────────────────────────

def test_list_filter_status(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&status=triaged&status=closed")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["status"] in ("triaged", "closed")


def test_list_filter_building_id(ac, db_conn):
    bid = db_conn.execute(
        "SELECT building_id FROM maintenance_request WHERE start_date BETWEEN %s AND %s AND building_id IS NOT NULL LIMIT 1",
        [_START, _END],
    ).fetchone()["building_id"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&building_id={bid}")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["building_id"] == bid


def test_list_filter_sector_id(ac, db_conn):
    sid = db_conn.execute(
        "SELECT sector_id FROM maintenance_request WHERE start_date BETWEEN %s AND %s AND sector_id IS NOT NULL LIMIT 1",
        [_START, _END],
    ).fetchone()["sector_id"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sector_id={sid}")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["sector_id"] == sid


def test_list_filter_assigned_employee_id(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&assigned_employee_id={_TECH_ASSIGNED}")
    assert r.status_code == 200
    assert r.json()["total"] > 0
    for item in r.json()["items"]:
        assert item["assigned_employee_id"] == _TECH_ASSIGNED


def test_list_filter_urgency(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&urgency=AJD")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["urgency_tier"] == "AJD"


def test_list_filter_source_calendar(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&source_calendar=st_maj")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["source_calendar"] == "st_maj"
        assert item["source_calendar_label"] == "Butler/Majordome"


# ── Sorting ────────────────────────────────────────────────────────────────────

def test_list_sort_by_start_date_asc(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=start_date&sort_dir=asc&limit=10")
    assert r.status_code == 200
    dates = [i["start_date"] for i in r.json()["items"] if i["start_date"]]
    assert dates == sorted(dates)


def test_list_sort_by_start_date_desc(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=start_date&sort_dir=desc&limit=10")
    assert r.status_code == 200
    dates = [i["start_date"] for i in r.json()["items"] if i["start_date"]]
    assert dates == sorted(dates, reverse=True)


def test_list_sort_by_status(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=status&sort_dir=asc&limit=50")
    assert r.status_code == 200
    statuses = [i["status"] for i in r.json()["items"]]
    assert statuses == sorted(statuses)


def test_list_sort_by_urgency_nulls_last(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=urgency_tier&sort_dir=asc&limit=50")
    assert r.status_code == 200
    tiers = [i["urgency_tier"] for i in r.json()["items"]]
    # All NULLs must be at the end
    non_null = [t for t in tiers if t is not None]
    null_count = tiers.count(None)
    assert tiers == non_null + [None] * null_count


# ── Pagination ─────────────────────────────────────────────────────────────────

def test_list_pagination_limit(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=5")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 5


def test_list_pagination_offset(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r1 = c.get(f"/api/v1/requests?{_BASE}&limit=5&offset=0")
    r2 = c.get(f"/api/v1/requests?{_BASE}&limit=5&offset=5")
    ids1 = {i["request_id"] for i in r1.json()["items"]}
    ids2 = {i["request_id"] for i in r2.json()["items"]}
    assert ids1.isdisjoint(ids2)


def test_list_limit_max_200_enforced(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=201")
    assert r.status_code == 422


def test_list_response_includes_total(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=1")
    body = r.json()
    assert body["total"] >= len(body["items"])


# ── Role visibility — list ─────────────────────────────────────────────────────

def test_list_coordinator_sees_all(ac, db_conn):
    total_all = db_conn.execute(
        "SELECT count(*) AS n FROM maintenance_request WHERE start_date BETWEEN %s AND %s",
        [_START, _END],
    ).fetchone()["n"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=1")
    assert r.json()["total"] == total_all


def test_list_director_sees_all(ac, db_conn):
    total_all = db_conn.execute(
        "SELECT count(*) AS n FROM maintenance_request WHERE start_date BETWEEN %s AND %s",
        [_START, _END],
    ).fetchone()["n"]
    c = ac(_user(_DIR_EMP, "director"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=1")
    assert r.json()["total"] == total_all


def test_list_technician_sees_only_scoped_requests(ac, db_conn):
    # Tech 1 (Alain Lepire, sector 5) — count their scoped requests
    scoped_count = db_conn.execute("""
        SELECT count(*) AS n FROM maintenance_request mr
        WHERE mr.start_date BETWEEN %s AND %s
        AND (
            mr.assigned_employee_id = 1
            OR mr.building_id IN (
                SELECT b.building_id FROM building b
                JOIN employee e ON b.sector_id = e.sector_id WHERE e.employee_id = 1
                UNION
                SELECT building_id FROM employee_building_assignment WHERE employee_id = 1
            )
        )
    """, [_START, _END]).fetchone()["n"]
    c = ac(_user(1, "technician"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=1")
    assert r.status_code == 200
    assert r.json()["total"] == scoped_count


def test_list_contractor_sees_only_assigned(ac, db_conn):
    assigned_count = db_conn.execute(
        "SELECT count(*) AS n FROM maintenance_request "
        "WHERE assigned_employee_id = %s AND start_date BETWEEN %s AND %s",
        [_CONTRACTOR_EMP, _START, _END],
    ).fetchone()["n"]
    c = ac(_user(_CONTRACTOR_EMP, "contractor"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=1")
    assert r.status_code == 200
    assert r.json()["total"] == assigned_count


# ── Role visibility — detail ───────────────────────────────────────────────────

def test_detail_coordinator_sees_pii(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 200
    body = r.json()
    assert body["caller_name"] is not None
    assert body["caller_phone"] is not None


def test_detail_director_sees_pii(ac):
    c = ac(_user(_DIR_EMP, "director"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 200
    assert r.json()["caller_name"] is not None


def test_detail_technician_assigned_sees_pii(ac):
    # Tech 24 is directly assigned to request 1909 — case-scoped PII visible
    c = ac(_user(_TECH_ASSIGNED, "technician"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 200
    assert r.json()["caller_name"] is not None


def test_detail_technician_sector_visible_pii_nulled(ac):
    # Tech 11 (sector 6) can see request 1909 via sector scope but is NOT the
    # assigned employee — contact fields must be null.
    c = ac(_user(_TECH_SECTOR, "technician"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 200
    body = r.json()
    assert body["caller_name"]  is None
    assert body["caller_phone"] is None
    assert body["caller_email"] is None
    assert body["caller_tenant_id"] is None


def test_detail_technician_out_of_scope_is_404(ac):
    # Tech 14 (sector 1) cannot see request 1909 (sector 6, not assigned)
    c = ac(_user(_TECH_OUT, "technician"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_detail_technician_own_assigned_is_200(ac):
    c = ac(_user(1, "technician"))
    r = c.get("/api/v1/requests/884")  # assigned to tech 1
    assert r.status_code == 200


def test_detail_contractor_assigned_is_200(ac, db_conn):
    req_id = db_conn.execute(
        "SELECT request_id FROM maintenance_request WHERE assigned_employee_id = %s AND start_date BETWEEN %s AND %s LIMIT 1",
        [_CONTRACTOR_EMP, _START, _END],
    ).fetchone()["request_id"]
    c = ac(_user(_CONTRACTOR_EMP, "contractor"))
    r = c.get(f"/api/v1/requests/{req_id}")
    assert r.status_code == 200


def test_detail_contractor_other_request_is_404(ac):
    # Request 1909 is assigned to tech 24, not contractor 2
    c = ac(_user(_CONTRACTOR_EMP, "contractor"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 404


def test_detail_includes_missing_fields_as_null(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_PII}")
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_cost"]      is None
    assert body["next_follow_up_date"] is None
    assert body["next_steps"]          is None


# ── Follow-up log ──────────────────────────────────────────────────────────────

def test_detail_includes_followup_log(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_LOG}")
    assert r.status_code == 200
    log = r.json()["followup_log"]
    assert len(log) >= 2
    assert all("followup_id" in e and "entry_text" in e for e in log)


def test_detail_followup_log_ordered_chronologically(ac, db_conn):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_LOG}")
    assert r.status_code == 200
    dates = [e["entry_date"] for e in r.json()["followup_log"] if e["entry_date"]]
    assert dates == sorted(dates)


def test_detail_request_with_no_followup_has_empty_log(ac, db_conn):
    # Find a request with no followup entries
    row = db_conn.execute("""
        SELECT mr.request_id FROM maintenance_request mr
        WHERE mr.start_date BETWEEN %s AND %s
        AND NOT EXISTS (
            SELECT 1 FROM maintenance_followup_entry fe WHERE fe.request_id = mr.request_id
        )
        LIMIT 1
    """, [_START, _END]).fetchone()
    assert row, "Expected a request with no followup entries"
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests/{row['request_id']}")
    assert r.status_code == 200
    assert r.json()["followup_log"] == []


# ── Lookup endpoints ───────────────────────────────────────────────────────────

def test_lookup_sectors_returns_list(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get("/api/v1/lookup/sectors")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all("sector_id" in s and "territoire" in s for s in items)


def test_lookup_buildings_returns_list(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get("/api/v1/lookup/buildings")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_lookup_buildings_filter_by_sector(ac, db_conn):
    sid = db_conn.execute(
        "SELECT sector_id FROM sector LIMIT 1"
    ).fetchone()["sector_id"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/lookup/buildings?sector_id={sid}")
    assert r.status_code == 200
    for b in r.json():
        assert b["sector_id"] == sid


def test_lookup_employees_coord_director_ok(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get("/api/v1/lookup/employees")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_lookup_employees_technician_is_403(ac):
    c = ac(_user(1, "technician"))
    r = c.get("/api/v1/lookup/employees")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PERMISSION_DENIED"


# ── Date ordering ──────────────────────────────────────────────────────────────

def test_list_end_before_start_is_422(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get("/api/v1/requests?start_date=2026-09-10&end_date=2026-09-01")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


# ── Internal field stripping for tech/contractor ───────────────────────────────

def test_detail_technician_strips_internal_fields(ac, db_conn):
    # Confirm that triage_summary (and other internal admin fields) are always
    # null for a technician, even when directly assigned.
    row = db_conn.execute("""
        SELECT mr.request_id FROM maintenance_request mr
        WHERE mr.triage_summary IS NOT NULL
        AND (
            mr.assigned_employee_id = %(emp_id)s
            OR mr.building_id IN (
                SELECT b.building_id FROM building b
                JOIN employee e ON b.sector_id = e.sector_id WHERE e.employee_id = %(emp_id)s
                UNION
                SELECT building_id FROM employee_building_assignment WHERE employee_id = %(emp_id)s
            )
        )
        LIMIT 1
    """, {"emp_id": _TECH_ASSIGNED}).fetchone()
    assert row, "Expected a request with non-null triage_summary visible to tech"
    rid = row["request_id"]

    # Coordinator confirms the field is non-null in the DB.
    coord_r = ac(_user(_COORD_EMP, "coordinator")).get(f"/api/v1/requests/{rid}")
    assert coord_r.status_code == 200
    assert coord_r.json()["triage_summary"] is not None

    # Technician (directly assigned) must not receive any internal field.
    tech_r = ac(_user(_TECH_ASSIGNED, "technician")).get(f"/api/v1/requests/{rid}")
    assert tech_r.status_code == 200
    body = tech_r.json()
    assert body["triage_summary"]  is None
    assert body["delegable_notes"] is None
    assert body["report_notes"]    is None
    assert body["other_notes"]     is None


# ── Extended PII case-scoping (occupants_raw / tenant_agreement_notes) ─────────

def test_detail_technician_assigned_sees_occupants(ac):
    # Tech 41 is directly assigned to request 1445 — case-scoped PII visible.
    c = ac(_user(_TECH_ASSIGNED_1445, "technician"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_OCCUPANTS}")
    assert r.status_code == 200
    assert r.json()["occupants_raw"] is not None


def test_detail_technician_sector_visible_occupants_nulled(ac):
    # Tech 11 (sector 6) sees request 1445 via sector scope but is NOT the
    # assigned employee — occupants_raw and tenant_agreement_notes must be null.
    c = ac(_user(_TECH_SECTOR, "technician"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_OCCUPANTS}")
    assert r.status_code == 200
    body = r.json()
    assert body["occupants_raw"]          is None
    assert body["tenant_agreement_notes"] is None


def test_detail_coordinator_sees_occupants(ac):
    # Coordinators always receive occupants_raw regardless of assignment.
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests/{_REQ_WITH_OCCUPANTS}")
    assert r.status_code == 200
    assert r.json()["occupants_raw"] is not None


# ── Search (q param) ───────────────────────────────────────────────────────────

def test_list_search_by_asnu(ac, db_conn):
    row = db_conn.execute(
        "SELECT asnu FROM maintenance_request WHERE start_date BETWEEN %s AND %s AND asnu IS NOT NULL LIMIT 1",
        [_START, _END],
    ).fetchone()
    assert row, "Expected a request with non-null ASNU in the date range"
    asnu = row["asnu"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&q={asnu}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    for item in body["items"]:
        assert item["asnu"] == asnu


def test_list_search_by_title_case_insensitive(ac, db_conn):
    row = db_conn.execute(
        "SELECT raw_title FROM maintenance_request WHERE start_date BETWEEN %s AND %s AND raw_title IS NOT NULL AND length(raw_title) >= 6 LIMIT 1",
        [_START, _END],
    ).fetchone()
    assert row, "Expected a request with non-null raw_title in the date range"
    # Use an uppercase 4-char slice — ILIKE must match it
    fragment = row["raw_title"][:4].upper()
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&q={fragment}")
    assert r.status_code == 200
    assert r.json()["total"] > 0


def test_list_search_no_match_returns_empty(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&q=ZZZNOMATCH999XYZ")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_search_scope_respected_for_technician(ac, db_conn):
    # Tech 1's scoped total with a broad search must be <= coordinator's total.
    c_coord = ac(_user(_COORD_EMP, "coordinator"))
    c_tech  = ac(_user(1, "technician"))
    r_coord = c_coord.get(f"/api/v1/requests?{_BASE}&q=a")
    r_tech  = c_tech.get(f"/api/v1/requests?{_BASE}&q=a")
    assert r_coord.status_code == 200
    assert r_tech.status_code == 200
    assert r_tech.json()["total"] <= r_coord.json()["total"]


# ── Last followup in list response ─────────────────────────────────────────────

def test_list_last_followup_populated(ac, db_conn):
    row = db_conn.execute("""
        SELECT mr.request_id FROM maintenance_request mr
        WHERE mr.start_date BETWEEN %s AND %s
        AND EXISTS (
            SELECT 1 FROM maintenance_followup_entry fe WHERE fe.request_id = mr.request_id
        )
        LIMIT 1
    """, [_START, _END]).fetchone()
    assert row, "Expected a request with followup entries in the date range"
    rid = row["request_id"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=200&offset=0")
    assert r.status_code == 200
    items = {i["request_id"]: i for i in r.json()["items"]}
    if rid in items:
        item = items[rid]
        assert item["last_followup_date"] is not None
        assert item["last_followup_text"] is not None


def test_list_last_followup_null_for_no_entries(ac, db_conn):
    row = db_conn.execute("""
        SELECT mr.request_id FROM maintenance_request mr
        WHERE mr.start_date BETWEEN %s AND %s
        AND NOT EXISTS (
            SELECT 1 FROM maintenance_followup_entry fe WHERE fe.request_id = mr.request_id
        )
        LIMIT 1
    """, [_START, _END]).fetchone()
    assert row, "Expected a request with no followup entries in the date range"
    rid = row["request_id"]
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&limit=200&offset=0")
    assert r.status_code == 200
    items = {i["request_id"]: i for i in r.json()["items"]}
    if rid in items:
        item = items[rid]
        assert item["last_followup_date"] is None


def test_list_sort_by_last_followup_date(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=last_followup_date&sort_dir=asc&limit=50")
    assert r.status_code == 200
    dates = [i["last_followup_date"] for i in r.json()["items"] if i["last_followup_date"]]
    nulls = [i for i in r.json()["items"] if i["last_followup_date"] is None]
    assert dates == sorted(dates)
    # NULLs at end
    all_dates = [i["last_followup_date"] for i in r.json()["items"]]
    null_count = all_dates.count(None)
    assert all_dates == [d for d in all_dates if d is not None] + [None] * null_count


def test_list_sort_by_estimated_cost(ac):
    # All current rows have NULL cost; endpoint must accept the sort key and
    # return 200 with NULLs last (trivially satisfied when all are NULL).
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=estimated_cost&sort_dir=asc&limit=10")
    assert r.status_code == 200
    assert all(i["estimated_cost"] is None for i in r.json()["items"])


def test_list_sort_by_next_follow_up_date(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=next_follow_up_date&sort_dir=asc&limit=10")
    assert r.status_code == 200
    assert all(i["next_follow_up_date"] is None for i in r.json()["items"])


def test_list_sort_by_next_steps(ac):
    c = ac(_user(_COORD_EMP, "coordinator"))
    r = c.get(f"/api/v1/requests?{_BASE}&sort_by=next_steps&sort_dir=asc&limit=10")
    assert r.status_code == 200
    assert all(i["next_steps"] is None for i in r.json()["items"])
