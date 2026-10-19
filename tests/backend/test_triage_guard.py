"""Triage writers must never overwrite a status that is no longer
triage_pending (fix ticket 2026-10-19). Covers the success writer
(_write_result) and the exhausted-retries writer (_mark_failed)."""
from __future__ import annotations

import logging

import psycopg.rows
import pytest

from backend.triage.service import _mark_failed, _write_result


def _triage_cursor(db_conn):
    # The triage service runs with positional (tuple) rows; match it.
    return db_conn.cursor(row_factory=psycopg.rows.tuple_row)


@pytest.fixture
def mk_request(db_conn):
    def _mk(status: str) -> int:
        return db_conn.execute(
            "INSERT INTO maintenance_request (status, raw_title) "
            "VALUES (%s, 'Triage guard test') RETURNING request_id",
            [status],
        ).fetchone()["request_id"]
    return _mk


def _status(db_conn, rid: int) -> str:
    return db_conn.execute(
        "SELECT status::text AS s FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()["s"]


def _provenance_count(db_conn, rid: int) -> int:
    return db_conn.execute(
        "SELECT count(*) AS n FROM data_provenance "
        "WHERE target_table = 'maintenance_request' AND target_pk = %s", [str(rid)]
    ).fetchone()["n"]


# ── Success writer ─────────────────────────────────────────────────────────────

def test_write_result_skips_when_status_changed(db_conn, mk_request, caplog):
    rid = mk_request("en_route")
    before = _provenance_count(db_conn, rid)
    with caplog.at_level(logging.WARNING, logger="backend.triage"):
        with _triage_cursor(db_conn) as cur:
            _write_result(cur, rid, {"title": "NE DOIT PAS ÊTRE ÉCRIT"}, "test-model")
    assert _status(db_conn, rid) == "en_route"  # untouched
    row = db_conn.execute(
        "SELECT problem_summary, triage_model_version FROM maintenance_request "
        "WHERE request_id = %s", [rid]).fetchone()
    assert row["problem_summary"] is None
    assert row["triage_model_version"] is None
    assert _provenance_count(db_conn, rid) == before  # nothing else written
    assert any(str(rid) in r.message and "no longer triage_pending" in r.message
               for r in caplog.records)


def test_write_result_applies_when_pending(db_conn, mk_request):
    rid = mk_request("triage_pending")
    with _triage_cursor(db_conn) as cur:
        _write_result(cur, rid, {"title": "Résumé triage"}, "test-model")
    assert _status(db_conn, rid) == "triaged"
    row = db_conn.execute(
        "SELECT problem_summary FROM maintenance_request WHERE request_id = %s", [rid]
    ).fetchone()
    assert row["problem_summary"] == "Résumé triage"


# ── Failure writer ─────────────────────────────────────────────────────────────

def test_mark_failed_skips_when_status_changed(db_conn, mk_request, caplog):
    rid = mk_request("triaged")
    with caplog.at_level(logging.WARNING, logger="backend.triage"):
        with _triage_cursor(db_conn) as cur:
            _mark_failed(cur, rid)
    assert _status(db_conn, rid) == "triaged"  # untouched
    assert any(str(rid) in r.message and "no longer triage_pending" in r.message
               for r in caplog.records)


def test_mark_failed_applies_when_pending(db_conn, mk_request):
    rid = mk_request("triage_pending")
    with _triage_cursor(db_conn) as cur:
        _mark_failed(cur, rid)
    assert _status(db_conn, rid) == "triage_failed"
