# provenance.py — shared provenance utility for ingestion scripts.
# Call log_provenance() for every field written.
# To write: call flush_to_db(conn) — flushes buffer and inserts in one step.
# flush() still available for callers that build their own INSERT batch.

from psycopg2.extras import execute_values

_buffer: list[dict] = []


def log_provenance(
    target_table: str,
    target_pk: int,
    target_column: str,
    source_type: str,
    source_drive_id: str | None,
    source_file_name: str | None,
    source_tab: str | None,
    source_row: str | None,
    source_column: str | None,
    raw_value,
    ingested_value,
) -> None:
    _buffer.append({
        "target_table":     target_table,
        "target_pk":        target_pk,
        "target_column":    target_column,
        "source_type":      source_type,
        "source_drive_id":  source_drive_id,
        "source_file_name": source_file_name,
        "source_tab":       source_tab,
        "source_row":       source_row,
        "source_column":    source_column,
        "raw_value":        str(raw_value) if raw_value is not None else None,
        "ingested_value":   str(ingested_value) if ingested_value is not None else None,
    })


def flush() -> list[dict]:
    """Return all buffered provenance rows and clear the buffer."""
    rows = list(_buffer)
    _buffer.clear()
    return rows


def flush_to_db(conn) -> int:
    """Flush buffer and insert provenance rows into data_provenance. Returns count written."""
    rows = flush()
    if not rows:
        return 0
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(provenance_id), 0) FROM data_provenance")
    offset = cur.fetchone()[0]
    execute_values(
        cur,
        "INSERT INTO data_provenance (provenance_id, target_table, target_pk,"
        " target_column, source_type, source_drive_id, source_file_name, source_tab,"
        " source_row, source_column, raw_value, ingested_value, ingested_at) VALUES %s",
        [(offset + i + 1, r["target_table"], r["target_pk"], r["target_column"],
          r["source_type"], r["source_drive_id"], r["source_file_name"], r["source_tab"],
          r["source_row"], r["source_column"], r["raw_value"], r["ingested_value"], None)
         for i, r in enumerate(rows)],
        page_size=5000,
    )
    return len(rows)
