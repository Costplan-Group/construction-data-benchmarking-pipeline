"""Unit tests for staging insert helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pyodbc

from ingestion_engine.staging.insert import get_decimal_metadata, insert_dataframe_rows


def test_insert_dataframe_rows_empty_and_success():
    conn = MagicMock()
    insert_dataframe_rows(conn, "stg.T", [])
    conn.cursor.assert_not_called()

    cur = MagicMock()
    conn.cursor.return_value = cur
    insert_dataframe_rows(conn, "stg.T", [{"A": 1, "B": 2}])
    cur.executemany.assert_called_once()
    conn.commit.assert_called()


def test_insert_dataframe_rows_hy090_fallback():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur

    def failing_fast(*_a, **_k):
        raise pyodbc.Error("HY090", "bad")

    # First executemany fails with HY090; second cursor path succeeds.
    calls = {"n": 0}

    def executemany(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise pyodbc.Error("HY090", "bad")

    cur.executemany.side_effect = executemany
    insert_dataframe_rows(conn, "stg.T", [{"A": 1}])
    assert calls["n"] == 2


def test_get_decimal_metadata():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = [("Amount", 18, 2)]
    meta = get_decimal_metadata("stg.Adjustments", lambda: conn)
    assert meta == {"Amount": (18, 2)}
    conn.close.assert_called_once()
