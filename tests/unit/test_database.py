"""Unit tests for Database wrapper with mocked connections."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ingestion_engine.config import IngestionConfig
from ingestion_engine.database import Database


def _fake_conn(rows=None, description=None):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    cur.description = description
    return conn, cur


def test_database_execute_fetch_and_transaction():
    conn, cur = _fake_conn(rows=[(1,)], description=[("id",), ("name",)])
    cur.fetchall.return_value = [(1, "a")]
    db = Database(connection_factory=lambda: conn)

    db.execute("UPDATE x", (1,))
    cur.execute.assert_called()
    conn.commit.assert_called()

    assert db.fetch_one("SELECT 1") == (1,)
    assert db.fetch_all("SELECT id, name") == [{"id": 1, "name": "a"}]

    with db.transaction() as txn:
        assert txn is db
        db.execute("INSERT", commit=False)
    conn.commit.assert_called()


def test_database_connect_requires_string_or_factory():
    db = Database()
    with pytest.raises(ValueError, match="connection_string or connection_factory"):
        db.connect()


def test_database_from_config():
    with patch(
        "ingestion_engine.database.get_ingestion_config",
        return_value=IngestionConfig(
            sql_server="S",
            sql_db="D",
            _env_file=None,
        ),
    ):
        db = Database.from_config(connection_factory=MagicMock)
        assert db._connection_string
