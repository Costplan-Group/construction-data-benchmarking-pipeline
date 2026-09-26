"""Unit tests for IngestionResult and connection helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ingestion_engine.config import IngestionConfig
from ingestion_engine.connection import get_connection, module_db
from ingestion_engine.enums import BatchStatus
from ingestion_engine.results import IngestionResult


def test_ingestion_result_as_dict():
    result = IngestionResult(
        load_batch_id="b1",
        status=BatchStatus.COMMITTED,
        error_count=2,
        source_file_name="a.xlsx",
    )
    payload = result.as_dict()
    assert payload["status"] == "COMMITTED"
    assert payload["error_count"] == 2


def test_module_db_and_get_connection():
    cfg = IngestionConfig(sql_server="S", sql_db="D", _env_file=None)
    with patch("ingestion_engine.connection.get_ingestion_config", return_value=cfg):
        db = module_db(connection_factory=MagicMock)
        assert db._connection_string

        fake = MagicMock()
        cur = MagicMock()
        fake.cursor.return_value = cur
        with patch("ingestion_engine.connection.pyodbc.connect", return_value=fake):
            conn = get_connection()
            assert conn is fake
            cur.execute.assert_called()
