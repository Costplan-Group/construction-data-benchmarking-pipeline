"""Load-batch persistence for Excel ingestion."""

from __future__ import annotations

import uuid
from typing import Any

from ingestion_engine.database import Database
from ingestion_engine.enums import BatchStatus, Severity


class LoadBatchRepository:
    _db: Database

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, file_name: str, source_file_path: str) -> str:
        load_batch_id = str(uuid.uuid4())
        self._db.execute(
            """
            INSERT INTO stg.LoadBatch (
                LoadBatchID,
                SourceFileName,
                SourceFilePath,
                BatchStatus
            )
            VALUES (?, ?, ?, ?)
            """,
            (load_batch_id, file_name, source_file_path, BatchStatus.RECEIVED.value),
        )
        return load_batch_id

    def update_status(self, load_batch_id: str, status: str | BatchStatus) -> None:
        status_value = status.value if isinstance(status, BatchStatus) else status
        self._db.execute_with_lock_retry(
            """
            UPDATE stg.LoadBatch
            SET BatchStatus = ?
            WHERE LoadBatchID = ?
            """,
            (status_value, load_batch_id),
        )

    def update_error_count(self, load_batch_id: str) -> None:
        self._db.execute_with_lock_retry(
            """
            UPDATE lb
            SET ErrorCount = x.ErrorCount
            FROM stg.LoadBatch lb
            CROSS APPLY (
                SELECT COUNT(*) AS ErrorCount
                FROM stg.ValidationError ve
                WHERE ve.LoadBatchID = lb.LoadBatchID
                  AND ve.Severity = ?
            ) x
            WHERE lb.LoadBatchID = ?
            """,
            (Severity.ERROR.value, load_batch_id),
        )

    def get_summary(self, load_batch_id: str) -> dict[str, Any] | None:
        rows = self._db.fetch_all(
            """
            SELECT
                LoadBatchID,
                SourceFileName,
                SourceFilePath,
                BatchStatus,
                ErrorCount,
                CreatedAt
            FROM stg.LoadBatch
            WHERE LoadBatchID = ?
            """,
            (load_batch_id,),
        )
        return rows[0] if rows else None

    def run_sql_validation(self, load_batch_id: str) -> None:
        self._db.execute("EXEC stg.usp_ValidateBatch ?", (load_batch_id,))

    def run_sql_commit(self, load_batch_id: str) -> None:
        self._db.execute("EXEC stg.usp_CommitBatch ?", (load_batch_id,))
