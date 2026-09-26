"""Bulk insert helpers for staging tables."""

from __future__ import annotations

import pyodbc


def insert_dataframe_rows(conn, table_name: str, rows: list[dict], *, commit: bool = True) -> None:
    if not rows:
        return

    columns = list(rows[0].keys())
    col_sql = ", ".join(columns)
    placeholder_sql = ", ".join(["?"] * len(columns))

    sql = f"INSERT INTO {table_name} ({col_sql}) VALUES ({placeholder_sql})"

    values = []
    for row in rows:
        values.append(tuple(row.get(col) for col in columns))

    cur = conn.cursor()
    try:
        cur.fast_executemany = True
        cur.executemany(sql, values)
        if commit:
            conn.commit()
    except pyodbc.Error as exc:
        msg = str(exc)
        if "HY090" not in msg:
            raise
        try:
            cur.close()
        except Exception:
            pass
        cur = conn.cursor()
        try:
            cur.fast_executemany = False
            cur.executemany(sql, values)
            if commit:
                conn.commit()
        finally:
            cur.close()
    finally:
        try:
            cur.close()
        except Exception:
            pass


def get_decimal_metadata(table_full_name: str, connection_factory) -> dict[str, tuple[int, int]]:
    schema, table = table_full_name.split(".")
    conn = connection_factory()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COLUMN_NAME, NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
              AND DATA_TYPE IN ('decimal', 'numeric')
            """,
            (schema, table),
        )
        out: dict[str, tuple[int, int]] = {}
        for row in cur.fetchall():
            out[str(row[0])] = (int(row[1]), int(row[2]))
        return out
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()
