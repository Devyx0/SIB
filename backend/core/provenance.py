"""Audit trail for edits made in the app: one data_provenance row per changed column."""
from __future__ import annotations


def write_provenance(
    conn, *, target_table: str, target_pk: str, target_column: str,
    employee_id: int, previous_value: str | None, new_value: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO data_provenance
            (target_table, target_pk, target_column, source_type, employee_id,
             previous_value, raw_value, ingested_value, ingested_at)
        VALUES (%(target_table)s, %(target_pk)s, %(target_column)s, 'app', %(employee_id)s,
                %(previous_value)s, %(new_value)s, %(new_value)s, NOW())
        """,
        {
            "target_table": target_table, "target_pk": target_pk,
            "target_column": target_column, "employee_id": employee_id,
            "previous_value": previous_value, "new_value": new_value,
        },
    )
