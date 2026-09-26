"""End-to-end Excel ingestion pipeline."""

from __future__ import annotations

import io
import logging
import traceback
from collections.abc import Callable

from ingestion_engine.connection import get_connection, module_db
from ingestion_engine.database import Database
from ingestion_engine.enums import BatchStatus, ErrorType, Severity
from ingestion_engine.results import IngestionResult
from ingestion_engine.staging.orchestrator import stage_all_sheets
from ingestion_engine.validation.report import validate_workbook_data
from ingestion_engine.workbook.reader import WorkbookReader

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        *,
        workbook_reader: WorkbookReader | None = None,
        connection_factory: Callable = get_connection,
        database_factory: Callable[[], Database] | None = None,
        insert_rows: Callable | None = None,
        get_decimal_metadata: Callable | None = None,
        resolve_sector_code: Callable | None = None,
        fetch_all: Callable | None = None,
        log_validation_error: Callable | None = None,
        create_load_batch: Callable | None = None,
        update_batch_status: Callable | None = None,
        update_batch_error_count: Callable | None = None,
        get_error_count: Callable | None = None,
        run_sql_validation: Callable | None = None,
        run_sql_commit: Callable | None = None,
    ):
        self.workbook_reader = workbook_reader or WorkbookReader()
        self.connection_factory = connection_factory
        self._database_factory = database_factory or (
            lambda: module_db(connection_factory=connection_factory)
        )
        self.insert_rows = insert_rows
        self.get_decimal_metadata = get_decimal_metadata
        self.resolve_sector_code = resolve_sector_code
        self.fetch_all = fetch_all
        self.log_validation_error = log_validation_error
        self.create_load_batch = create_load_batch
        self.update_batch_status = update_batch_status
        self.update_batch_error_count = update_batch_error_count
        self.get_error_count = get_error_count
        self.run_sql_validation = run_sql_validation
        self.run_sql_commit = run_sql_commit

    def _repos(self, db: Database):
        from backend.app.repositories.load_batch import LoadBatchRepository
        from backend.app.repositories.validation_error import ValidationErrorRepository

        return LoadBatchRepository(db), ValidationErrorRepository(db)

    def run(
        self, excel_stream: io.BytesIO, source_file_name: str, source_path: str
    ) -> IngestionResult:
        db = self._database_factory()
        db.open()
        batch_repo, error_repo = self._repos(db)

        create_batch = self.create_load_batch or batch_repo.create
        update_status = self.update_batch_status or batch_repo.update_status
        update_error_count = self.update_batch_error_count or batch_repo.update_error_count
        count_errors = self.get_error_count or error_repo.count_errors
        log_error = self.log_validation_error or error_repo.log
        sql_validate = self.run_sql_validation or batch_repo.run_sql_validation
        sql_commit = self.run_sql_commit or batch_repo.run_sql_commit

        load_batch_id = create_batch(source_file_name, source_path)
        db.commit()

        try:
            dataframes = self.workbook_reader.read(excel_stream)

            with db.transaction():
                validate_workbook_data(load_batch_id, dataframes, error_repo=error_repo)
                initial_errors = count_errors(load_batch_id)
                update_error_count(load_batch_id)

                if initial_errors > 0:
                    update_status(load_batch_id, BatchStatus.FAILED)
                    return IngestionResult(
                        load_batch_id=load_batch_id,
                        status=BatchStatus.FAILED,
                        error_count=initial_errors,
                        source_file_name=source_file_name,
                    )

            insert_fn = self.insert_rows
            decimal_meta_fn = self.get_decimal_metadata
            if insert_fn is None or decimal_meta_fn is None:
                from ingestion_engine import excel_file_ingestion as facade

                insert_fn = insert_fn or facade.insert_dataframe_rows
                decimal_meta_fn = decimal_meta_fn or facade._get_decimal_metadata

            def _log(**kwargs):
                kwargs.setdefault("use_row_data_column", True)
                log_error(**kwargs)

            with db.transaction():
                stage_all_sheets(
                    load_batch_id,
                    source_file_name,
                    dataframes,
                    connection_factory=self.connection_factory,
                    insert_rows=insert_fn,
                    get_decimal_metadata=decimal_meta_fn,
                    log_validation_error=_log,
                    resolve_sector_code=self.resolve_sector_code,
                    fetch_all=self.fetch_all,
                    conn=db.connection,
                    commit=False,
                )
                update_status(load_batch_id, BatchStatus.STAGED)
                sql_validate(load_batch_id)
                sql_commit(load_batch_id)

                final_errors = count_errors(load_batch_id)
                update_error_count(load_batch_id)

                if final_errors > 0:
                    update_status(load_batch_id, BatchStatus.FAILED)
                    return IngestionResult(
                        load_batch_id=load_batch_id,
                        status=BatchStatus.FAILED,
                        error_count=final_errors,
                        source_file_name=source_file_name,
                    )

                update_status(load_batch_id, BatchStatus.COMMITTED)

            return IngestionResult(
                load_batch_id=load_batch_id,
                status=BatchStatus.COMMITTED,
                error_count=0,
                source_file_name=source_file_name,
            )

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            db.rollback()
            try:
                log_error(
                    load_batch_id=load_batch_id,
                    sheet_name=None,
                    row_num=None,
                    column_name=None,
                    error_type=ErrorType.EXCEPTION.value,
                    error_message=error_message + " | " + traceback.format_exc()[:700],
                    severity=Severity.ERROR.value,
                    use_row_data_column=True,
                )
                update_error_count(load_batch_id)
                update_status(load_batch_id, BatchStatus.FAILED)
                db.commit()
            except Exception:
                logger.exception(
                    "Could not persist ingestion exception for batch %s", load_batch_id
                )

            try:
                error_count = count_errors(load_batch_id)
            except Exception:
                error_count = 1

            return IngestionResult(
                load_batch_id=load_batch_id,
                status=BatchStatus.FAILED,
                error_count=error_count,
                exception=error_message,
                source_file_name=source_file_name,
            )
        finally:
            db.close()
