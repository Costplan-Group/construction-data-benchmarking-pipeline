"""Validation-error persistence for Excel ingestion."""

from __future__ import annotations

import json
from typing import Any

from ingestion_engine.database import Database
from ingestion_engine.enums import ErrorType, Severity


class ValidationErrorRepository:
    _db: Database

    def __init__(self, db: Database) -> None:
        self._db = db

    def log(
        self,
        load_batch_id: str,
        sheet_name: str | None = None,
        row_num: int | None = None,
        column_name: str | None = None,
        error_type: str | ErrorType = ErrorType.VALIDATION,
        error_message: str = "",
        severity: str | Severity = Severity.ERROR,
        row_data: dict[str, Any] | None = None,
        *,
        use_row_data_column: bool = True,
    ) -> None:
        """
        Persist one validation error.

        Row snapshots are stored in RowDataJson; ErrorMessage stays human-readable
        and is truncated to 1000 characters.
        """
        type_value = error_type.value if isinstance(error_type, ErrorType) else error_type
        severity_value = severity.value if isinstance(severity, Severity) else severity
        message = error_message or ""
        row_json: str | None = None

        if row_data is not None:
            try:
                row_json = json.dumps(row_data, default=str)
            except Exception:
                row_json = None

        if use_row_data_column:
            self._db.execute(
                """
                INSERT INTO stg.ValidationError (
                    LoadBatchID,
                    SheetName,
                    RowNum,
                    ColumnName,
                    ErrorType,
                    ErrorMessage,
                    Severity,
                    RowDataJson
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    load_batch_id,
                    sheet_name,
                    row_num,
                    column_name,
                    type_value,
                    message[:1000],
                    severity_value,
                    row_json,
                ),
            )
            return

        # Legacy fallback if RowDataJson column is unavailable.
        if row_json is not None:
            message = f"{message}||ROW_DATA_JSON||{row_json}"

        self._db.execute(
            """
            INSERT INTO stg.ValidationError (
                LoadBatchID,
                SheetName,
                RowNum,
                ColumnName,
                ErrorType,
                ErrorMessage,
                Severity
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                load_batch_id,
                sheet_name,
                row_num,
                column_name,
                type_value,
                message[:1000],
                severity_value,
            ),
        )

    def count_errors(self, load_batch_id: str) -> int:
        row = self._db.fetch_one(
            """
            SELECT COUNT(*)
            FROM stg.ValidationError
            WHERE LoadBatchID = ?
              AND Severity = ?
            """,
            (load_batch_id, Severity.ERROR.value),
        )
        return int(row[0]) if row else 0

    def error_counts(self, load_batch_id: str) -> list[dict[str, Any]]:
        return self._db.fetch_all(
            """
            SELECT
                Severity,
                ErrorType,
                SheetName,
                COUNT(*) AS Cnt
            FROM stg.ValidationError
            WHERE LoadBatchID = ?
            GROUP BY Severity, ErrorType, SheetName
            ORDER BY Cnt DESC
            """,
            (load_batch_id,),
        )

    def error_details(
        self, load_batch_id: str, *, include_row_data: bool = False
    ) -> list[dict[str, Any]]:
        row_data_select = ",\n            RowDataJson" if include_row_data else ""
        return self._db.fetch_all(
            f"""
            SELECT
                Severity,
                SheetName,
                RowNum,
                ColumnName,
                ErrorType,
                ErrorMessage{row_data_select}
            FROM stg.ValidationError
            WHERE LoadBatchID = ?
            ORDER BY
                CASE WHEN Severity = 'ERROR' THEN 0 ELSE 1 END,
                SheetName,
                RowNum
            """,
            (load_batch_id,),
        )
