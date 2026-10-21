"""Triage write path: recommended_tasks[] → proposal dispatch_task rows (Task 7)."""
from __future__ import annotations

import psycopg.rows
import pytest

from backend.triage.output_contract import validate
from backend.triage.service import _write_result


def _cur(db_conn):
    # The triage service runs with positional (tuple) rows; match it.
    return db_conn.cursor(row_factory=psycopg.rows.tuple_row)


def _parsed(**kw):
    d = {
        "verdict": "single",
        "duplicate_of_request_id": None,
        "addition_to_request_id": None,
        "title": "Fuite toilette et plancher abîmé",
        "problems": ["Fuite à la toilette", "Plancher gondolé"],
        "entry_permission": None,
        "urgency_tier": "URGENT",
        "complexity_tier": "C2",
        "congestion_level": "N2",
        "time_estimate_bucket": "H1_TO_2H",
        "delegable_status": "YES",
        "report_status": "CAN_WAIT",
        "routing_rule": "A0",
        "subcontractor_name": None,
        "vendor_id": None,
        "synergy_request_ids": [],
        "other_notes": None,
        "recommended_tasks": [
            {"description": "Réparer la fuite", "suggested_trade": "plomberie",
             "urgency_tier": "URGENT"},
            {"description": "Remplacer le plancher", "urgency_tier": "Faible",
             "subcontractor_name": "Fortin", "notes": "après la plomberie"},
        ],
    }
    d.update(kw)
    return d


@pytest.fixture
def mk_request(db_conn):
    def _mk(status: str = "triage_pending") -> int:
        return db_conn.execute(
            "INSERT INTO maintenance_request (status, raw_title) "
            "VALUES (%s::request_status, 'Triage tasks test') RETURNING request_id",
            [status],
        ).fetchone()["request_id"]
    return _mk


def _status(db_conn, rid):
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()["s"]


def _tasks(db_conn, rid):
    return db_conn.execute(
        "SELECT * FROM dispatch_task WHERE request_id = %s ORDER BY sort_order, task_id", [rid]
    ).fetchall()


def test_single_writes_proposals_and_triage_proposal(db_conn, mk_request):
    rid = mk_request()
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(), "test-model")
    assert _status(db_conn, rid) == "triage_proposal"
    rows = _tasks(db_conn, rid)
    assert [r["description"] for r in rows] == [
        "Réparer la fuite", "Remplacer le plancher\naprès la plomberie",
    ]
    for r in rows:
        assert r["accepted_at"] is None
        assert r["source"] == "ai_recommended"
        assert r["status"] == "queued"
        assert r["assigned_employee_id"] is None  # rule 37
        assert r["due_at"] is None
    assert [r["urgency_tier"] for r in rows] == ["URGENT", "Faible"]
    assert rows[1]["subcontractor_name"] == "Fortin"
    assert [r["sort_order"] for r in rows] == [0, 1]


def test_task_vendor_id_persisted(db_conn, mk_request):
    vid = db_conn.execute("SELECT vendor_id FROM vendor_contact LIMIT 1").fetchone()
    if vid is None:
        pytest.skip("no vendor_contact rows")
    rid = mk_request()
    tasks = [{"description": "Poser la porte", "vendor_id": vid["vendor_id"]}]
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(recommended_tasks=tasks), "test-model")
    assert _tasks(db_conn, rid)[0]["vendor_id"] == vid["vendor_id"]


def test_single_without_tasks_stays_triaged(db_conn, mk_request):
    """Legacy / defensive: a result with no tasks never parks a call in triage_proposal."""
    rid = mk_request()
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(recommended_tasks=[]), "test-model")
    assert _status(db_conn, rid) == "triaged"
    assert _tasks(db_conn, rid) == []


def test_duplicate_creates_no_tasks(db_conn, mk_request):
    peer = mk_request("open")
    rid = mk_request()
    parsed = _parsed(
        verdict="duplicate", duplicate_of_request_id=peer,
        title="DOUBLON POTENTIEL — Fuite", recommended_tasks=[{"description": "Ignorée"}],
    )
    with _cur(db_conn) as cur:
        _write_result(cur, rid, parsed, "test-model")
    assert _status(db_conn, rid) == "triaged"
    assert _tasks(db_conn, rid) == []
    assert _tasks(db_conn, peer) == []


def test_addition_puts_proposals_on_peer(db_conn, mk_request):
    peer = mk_request("open")
    rid = mk_request()
    parsed = _parsed(
        verdict="addition", addition_to_request_id=peer, routing_rule="A0",
        recommended_tasks=[{"description": "Réparer le mur", "urgency_tier": "Faible"}],
    )
    with _cur(db_conn) as cur:
        _write_result(cur, rid, parsed, "test-model")
    assert _status(db_conn, rid) == "closed"      # merged child
    assert _tasks(db_conn, rid) == []
    assert _status(db_conn, peer) == "open"       # not bounced back to triage_proposal
    rows = _tasks(db_conn, peer)
    assert len(rows) == 1
    assert rows[0]["description"] == "Réparer le mur"
    assert rows[0]["accepted_at"] is None and rows[0]["source"] == "ai_recommended"


def test_addition_without_tasks_is_fine(db_conn, mk_request):
    peer = mk_request("open")
    rid = mk_request()
    parsed = _parsed(verdict="addition", addition_to_request_id=peer, recommended_tasks=[])
    with _cur(db_conn) as cur:
        _write_result(cur, rid, parsed, "test-model")
    assert _status(db_conn, rid) == "closed"
    assert _tasks(db_conn, peer) == []


def test_addition_to_closed_peer_writes_no_tasks(db_conn, mk_request):
    peer = mk_request("closed")
    rid = mk_request()
    parsed = _parsed(
        verdict="addition", addition_to_request_id=peer, routing_rule="A0",
        recommended_tasks=[{"description": "Réparer le mur"}],
    )
    with _cur(db_conn) as cur:
        _write_result(cur, rid, parsed, "test-model")
    assert _tasks(db_conn, peer) == []


def test_exclusive_routing_addition_becomes_single_with_proposals(db_conn, mk_request):
    peer = mk_request("open")
    rid = mk_request()
    parsed = _parsed(verdict="addition", addition_to_request_id=peer, routing_rule="A1")
    with _cur(db_conn) as cur:
        _write_result(cur, rid, parsed, "test-model")
    assert _status(db_conn, rid) == "triage_proposal"
    assert len(_tasks(db_conn, rid)) == 2
    assert _tasks(db_conn, peer) == []


def test_status_changed_writes_no_tasks(db_conn, mk_request):
    rid = mk_request("en_route")
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(), "test-model")
    assert _status(db_conn, rid) == "en_route"
    assert _tasks(db_conn, rid) == []


def test_retriage_replaces_prior_ai_proposals_only(db_conn, mk_request):
    rid = mk_request()
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(), "test-model")
    # A dispatcher-made and an accepted AI task must survive a re-triage.
    db_conn.execute(
        "INSERT INTO dispatch_task (request_id, description, source, accepted_at) "
        "VALUES (%s, 'Manuel', 'dispatcher', now()), (%s, 'AI acceptée', 'ai_recommended', now())",
        [rid, rid],
    )
    db_conn.execute(
        "UPDATE maintenance_request SET status = 'triage_pending' WHERE request_id = %s", [rid]
    )
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(recommended_tasks=[{"description": "Nouvelle"}]), "test-model")
    descs = sorted(r["description"] for r in _tasks(db_conn, rid))
    assert descs == ["AI acceptée", "Manuel", "Nouvelle"]


def test_gate_rejects_unknown_task_vendor(db_conn, mk_request):
    rid = mk_request()
    parsed = _parsed(recommended_tasks=[{"description": "Poser la porte", "vendor_id": 987654321}])
    result, detail = validate(parsed, db_conn, rid)
    assert result == "rejected_invalid_recommended_tasks", detail


def test_prompt_documents_recommended_tasks():
    from backend.triage.system_prompt import _OUTPUT_CONTRACT
    assert '"recommended_tasks"' in _OUTPUT_CONTRACT
    assert "suggested_trade" in _OUTPUT_CONTRACT
    assert "at least one" in _OUTPUT_CONTRACT.lower()
    assert "no assignee" in _OUTPUT_CONTRACT.lower()


def test_max_tokens_leaves_room_for_tasks():
    import backend.triage.service as svc
    assert svc._MAX_TOKENS >= 2048


def test_exclusive_addition_without_tasks_fails_validation(db_conn, mk_request):
    """The addition→single rewrite must never reach the writer with zero tasks."""
    peer = mk_request("open")
    rid = mk_request()
    parsed = _parsed(verdict="addition", addition_to_request_id=peer, routing_rule="A1",
                     recommended_tasks=[])
    result, _ = validate(parsed, None, rid)
    assert result == "rejected_missing_recommended_tasks"


def test_task_vendor_fields_land_on_columns(db_conn, mk_request):
    vid = db_conn.execute("SELECT vendor_id FROM vendor_contact LIMIT 1").fetchone()
    rid = mk_request()
    tasks = [{"description": "Poser la porte", "subcontractor_name": "Duclos",
              **({"vendor_id": vid["vendor_id"]} if vid else {})}]
    with _cur(db_conn) as cur:
        _write_result(cur, rid, _parsed(routing_rule="A3", subcontractor_name="Duclos",
                                        recommended_tasks=tasks), "test-model")
    row = _tasks(db_conn, rid)[0]
    assert row["subcontractor_name"] == "Duclos"
    if vid:
        assert row["vendor_id"] == vid["vendor_id"]
