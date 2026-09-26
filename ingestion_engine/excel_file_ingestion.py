"""
Legacy façade for Excel ingestion.

Implementation lives in ingestion_engine.workbook, validation, staging, and pipeline.
This module re-exports stable entry points for tests and backend services.
"""

from __future__ import annotations

import io
import os

from ingestion_engine.coercion import (  # noqa: F401
    clean_value,
    normalize_text,
    to_bit,
    to_decimal,
    to_int,
)
from ingestion_engine.coercion import resolve_sector_code as _resolve_sector_code_impl
from ingestion_engine.config import get_ingestion_config
from ingestion_engine.connection import get_connection, module_db
from ingestion_engine.contractor import (  # noqa: F401
    detect_selected_contractor_from_sheet_row,
    detect_selected_contractor_from_workbook,
    get_selected_contractor,
    normalize_contractor_metrics,
    resolve_metric_column,
)
from ingestion_engine.database import Database
from ingestion_engine.enums import BatchStatus
from ingestion_engine.pipeline import IngestionPipeline
from ingestion_engine.results import IngestionResult
from ingestion_engine.row_utils import infer_l3_row_type, is_effectively_blank_row  # noqa: F401
from ingestion_engine.schema import (  # noqa: F401
    COLUMN_MAPS,
    REQUIRED_BASE_SHEETS,
    REQUIRED_COLUMNS,
    STAGING_TABLES,
    required_base_sheets,
)
from ingestion_engine.staging.insert import get_decimal_metadata as _get_decimal_metadata_impl
from ingestion_engine.staging.insert import insert_dataframe_rows
from ingestion_engine.staging.orchestrator import stage_all_sheets as _stage_all_sheets_impl
from ingestion_engine.validation.report import (
    validate_workbook_data as _validate_workbook_data_impl,
)
from ingestion_engine.workbook.aliases import SHEET_ALIASES, resolve_sheet_name  # noqa: F401

# ============================================================
# DB HELPERS (patch points for characterization tests)
# ============================================================


def _module_db() -> Database:
    return module_db(connection_factory=get_connection)


def execute_non_query(sql, params=None):
    _module_db().execute(sql, params, commit=True)


def fetch_one(sql, params=None):
    return _module_db().fetch_one(sql, params)


def fetch_all(sql, params=None):
    return _module_db().fetch_all(sql, params)


def resolve_sector_code(value: str | None) -> str | None:
    return _resolve_sector_code_impl(value, connection_factory=get_connection)


def _get_decimal_metadata(table_full_name: str) -> dict[str, tuple[int, int]]:
    return _get_decimal_metadata_impl(table_full_name, get_connection)


# ============================================================
# BATCH / VALIDATION ERROR REPOSITORIES
# ============================================================


def _load_batch_repo():
    from backend.app.repositories.load_batch import LoadBatchRepository

    return LoadBatchRepository(_module_db())


def _validation_error_repo():
    from backend.app.repositories.validation_error import ValidationErrorRepository

    return ValidationErrorRepository(_module_db())


def create_load_batch(file_name: str, source_file_path: str) -> str:
    return _load_batch_repo().create(file_name, source_file_path)


def update_batch_status(load_batch_id: str, status: str | BatchStatus):
    _load_batch_repo().update_status(load_batch_id, status)


def log_validation_error(
    load_batch_id: str,
    sheet_name: str | None = None,
    row_num: int | None = None,
    column_name: str | None = None,
    error_type: str = "VALIDATION",
    error_message: str = "",
    severity: str = "ERROR",
    row_data: dict | None = None,
):
    _validation_error_repo().log(
        load_batch_id=load_batch_id,
        sheet_name=sheet_name,
        row_num=row_num,
        column_name=column_name,
        error_type=error_type,
        error_message=error_message,
        severity=severity,
        row_data=row_data,
        use_row_data_column=True,
    )


def get_error_count(load_batch_id: str) -> int:
    return _validation_error_repo().count_errors(load_batch_id)


def update_batch_error_count(load_batch_id: str):
    _load_batch_repo().update_error_count(load_batch_id)


def validate_workbook_data(load_batch_id: str, dataframes: dict):
    def _log(load_batch_id, sheet_name=None, **kwargs):
        log_validation_error(load_batch_id, sheet_name=sheet_name, **kwargs)

    _validate_workbook_data_impl(load_batch_id, dataframes, log_fn=_log)


def stage_all_sheets(load_batch_id: str, source_file: str, dataframes: dict):
    _stage_all_sheets_impl(
        load_batch_id,
        source_file,
        dataframes,
        connection_factory=get_connection,
        insert_rows=insert_dataframe_rows,
        get_decimal_metadata=_get_decimal_metadata,
        log_validation_error=log_validation_error,
        resolve_sector_code=resolve_sector_code,
        fetch_all=fetch_all,
    )


def run_sql_validation(load_batch_id: str):
    _load_batch_repo().run_sql_validation(load_batch_id)


def run_sql_commit(load_batch_id: str):
    _load_batch_repo().run_sql_commit(load_batch_id)


def get_batch_summary(load_batch_id: str) -> dict | None:
    return _load_batch_repo().get_summary(load_batch_id)


def get_batch_error_counts(load_batch_id: str) -> list[dict]:
    return _validation_error_repo().error_counts(load_batch_id)


def get_batch_error_details(load_batch_id: str) -> list[dict]:
    return _validation_error_repo().error_details(load_batch_id, include_row_data=True)


def _default_pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        connection_factory=get_connection,
        database_factory=lambda: module_db(connection_factory=get_connection),
        insert_rows=insert_dataframe_rows,
        get_decimal_metadata=_get_decimal_metadata,
        resolve_sector_code=resolve_sector_code,
        fetch_all=fetch_all,
        log_validation_error=log_validation_error,
        create_load_batch=create_load_batch,
        update_batch_status=update_batch_status,
        update_batch_error_count=update_batch_error_count,
        get_error_count=get_error_count,
        run_sql_validation=run_sql_validation,
        run_sql_commit=run_sql_commit,
    )


def _process_excel_stream(
    excel_stream: io.BytesIO, source_file_name: str, source_path: str
) -> IngestionResult:
    return _default_pipeline().run(excel_stream, source_file_name, source_path)


def process_local_file(local_file_path: str) -> IngestionResult:
    file_name = os.path.basename(local_file_path)
    print(f"\nProcessing local file: {file_name}")
    with open(local_file_path, "rb") as f:
        excel_stream = io.BytesIO(f.read())
    result = _process_excel_stream(excel_stream, file_name, local_file_path)
    if result.status == BatchStatus.COMMITTED:
        print(f"COMMITTED: {file_name}")
    else:
        print(f"FAILED: {file_name}")
    return result


def process_uploaded_file(file_name: str, file_bytes: bytes) -> IngestionResult:
    excel_stream = io.BytesIO(file_bytes)
    return _process_excel_stream(excel_stream, file_name, f"upload://{file_name}")


def main():
    local_path = get_ingestion_config().local_test_file_path
    if local_path:
        process_local_file(local_path)
        return

    print("LOCAL_TEST_FILE_PATH is not set.")
    print("Set LOCAL_TEST_FILE_PATH in your .env for manual file testing.")


if __name__ == "__main__":
    main()
