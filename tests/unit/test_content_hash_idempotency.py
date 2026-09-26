"""Unit tests for workbook content-hash idempotency."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from ingestion_engine.content_hash import sha256_hex
from ingestion_engine.enums import BatchStatus
from ingestion_engine.pipeline import IngestionPipeline


def test_sha256_hex_is_stable():
    assert sha256_hex(b"abc") == sha256_hex(b"abc")
    assert sha256_hex(b"abc") != sha256_hex(b"abd")
    assert len(sha256_hex(b"abc")) == 64


def test_pipeline_links_duplicate_workbook_by_content_hash():
    file_bytes = b"fake-xlsx-bytes"
    content_hash = sha256_hex(file_bytes)
    existing_id = "11111111-1111-1111-1111-111111111111"

    batch_repo = MagicMock()
    batch_repo.find_by_content_hash.return_value = {
        "LoadBatchID": existing_id,
        "SourceFileName": "original.xlsx",
        "BatchStatus": "COMMITTED",
        "ErrorCount": 0,
        "ContentHash": content_hash,
    }
    error_repo = MagicMock()

    db = MagicMock()
    pipeline = IngestionPipeline(
        workbook_reader=MagicMock(),
        create_load_batch=MagicMock(side_effect=AssertionError("must not create")),
    )
    pipeline._database_factory = MagicMock(return_value=db)
    pipeline._repos = MagicMock(return_value=(batch_repo, error_repo))

    result = pipeline.run(io.BytesIO(file_bytes), "repeat.xlsx", "upload://repeat.xlsx")

    assert result.duplicate is True
    assert result.load_batch_id == existing_id
    assert result.status == BatchStatus.COMMITTED
    assert result.content_hash == content_hash
    assert result.source_file_name == "original.xlsx"
    batch_repo.create.assert_not_called()
    db.close.assert_called_once()


def test_pipeline_stores_content_hash_on_new_batch():
    file_bytes = b"new-workbook"
    content_hash = sha256_hex(file_bytes)
    created_id = "22222222-2222-2222-2222-222222222222"

    batch_repo = MagicMock()
    batch_repo.find_by_content_hash.return_value = None
    batch_repo.create.return_value = created_id
    error_repo = MagicMock()
    error_repo.count_errors.return_value = 0

    db = MagicMock()
    db.transaction.return_value.__enter__ = MagicMock(return_value=None)
    db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    db.connection = MagicMock()

    reader = MagicMock()
    reader.read.return_value = {}

    pipeline = IngestionPipeline(
        workbook_reader=reader,
        insert_rows=MagicMock(),
        get_decimal_metadata=MagicMock(return_value={}),
        run_sql_validation=MagicMock(),
        run_sql_commit=MagicMock(),
    )
    pipeline._database_factory = MagicMock(return_value=db)
    pipeline._repos = MagicMock(return_value=(batch_repo, error_repo))

    with (
        patch("ingestion_engine.pipeline.validate_workbook_data"),
        patch("ingestion_engine.pipeline.stage_all_sheets"),
    ):
        result = pipeline.run(
            io.BytesIO(file_bytes),
            "new.xlsx",
            "upload://new.xlsx",
        )

    assert result.duplicate is False
    assert result.load_batch_id == created_id
    assert result.content_hash == content_hash
    assert result.status == BatchStatus.COMMITTED
    batch_repo.create.assert_called_once_with("new.xlsx", "upload://new.xlsx", content_hash)
