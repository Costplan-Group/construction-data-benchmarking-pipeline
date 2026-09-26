"""End-to-end Excel ingestion pipeline."""

from __future__ import annotations

import io
import logging
from collections.abc import Callable

import pyodbc

from ingestion_engine.connection import get_connection, module_db
from ingestion_engine.content_hash import sha256_hex
from ingestion_engine.database import Database
from ingestion_engine.enums import BatchStatus, ErrorType, Severity
from ingestion_engine.results import IngestionResult
from ingestion_engine.staging.orchestrator import stage_all_sheets
from ingestion_engine.validation.report import validate_workbook_data
from ingestion_engine.workbook.reader import WorkbookReader

logger = logging.getLogger(__name__)


def _batch_extra(load_batch_id: str | None, **kwargs: object) -> dict[str, object]:
    payload: dict[str, object] = {"load_batch_id": load_batch_id}
    payload.update({k: v for k, v in kwargs.items() if v is not None})
    return payload


def _status_from_value(value: object) -> BatchStatus:
    if isinstance(value, BatchStatus):
        return value
    text = str(value or "").strip().upper()
    try:
        return BatchStatus(text)
    except ValueError:
        return BatchStatus.FAILED


def _result_from_existing_batch(
    existing: dict,
    *,
    source_file_name: str,
    content_hash: str,
) -> IngestionResult:
    return IngestionResult(
        load_batch_id=str(existing["LoadBatchID"]),
        status=_status_from_value(existing.get("BatchStatus")),
        error_count=int(existing.get("ErrorCount") or 0),
        source_file_name=existing.get("SourceFileName") or source_file_name,
        content_hash=content_hash,
        duplicate=True,
    )


def _is_duplicate_hash_error(exc: BaseException) -> bool:
    if isinstance(exc, pyodbc.IntegrityError):
        return True
    text = str(exc).lower()
    return (
        "ux_loadbatch_contenthash" in text
        or "2601" in text
        or "2627" in text
        or "unique" in text
        or "duplicate" in text
    )


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
        self,
        excel_stream: io.BytesIO,
        source_file_name: str,
        source_path: str,
        *,
        content_hash: str | None = None,
    ) -> IngestionResult:
        file_bytes = excel_stream.getvalue()
        content_hash = content_hash or sha256_hex(file_bytes)
        excel_stream = io.BytesIO(file_bytes)

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

        existing = batch_repo.find_by_content_hash(content_hash)
        if existing:
            linked = _result_from_existing_batch(
                existing,
                source_file_name=source_file_name,
                content_hash=content_hash,
            )
            logger.info(
                "Duplicate workbook linked load_batch_id=%s source_file=%s content_hash=%s",
                linked.load_batch_id,
                source_file_name,
                content_hash[:12],
                extra=_batch_extra(
                    linked.load_batch_id,
                    source_file_name=source_file_name,
                    content_hash=content_hash,
                    duplicate=True,
                    status=linked.status.value,
                ),
            )
            db.close()
            return linked

        try:
            try:
                load_batch_id = create_batch(source_file_name, source_path, content_hash)
            except TypeError:
                # Injected test doubles may still use the two-arg create signature.
                load_batch_id = create_batch(source_file_name, source_path)
        except Exception as exc:
            # Concurrent duplicate insert races the unique ContentHash index.
            raced = batch_repo.find_by_content_hash(content_hash)
            if raced is not None and _is_duplicate_hash_error(exc):
                linked = _result_from_existing_batch(
                    raced,
                    source_file_name=source_file_name,
                    content_hash=content_hash,
                )
                logger.info(
                    "Duplicate workbook race linked load_batch_id=%s content_hash=%s",
                    linked.load_batch_id,
                    content_hash[:12],
                    extra=_batch_extra(
                        linked.load_batch_id,
                        content_hash=content_hash,
                        duplicate=True,
                    ),
                )
                db.close()
                return linked
            db.close()
            raise

        logger.info(
            "Load batch created load_batch_id=%s source_file=%s content_hash=%s",
            load_batch_id,
            source_file_name,
            content_hash[:12],
            extra=_batch_extra(
                load_batch_id,
                source_file_name=source_file_name,
                content_hash=content_hash,
            ),
        )

        try:
            dataframes = self.workbook_reader.read(excel_stream)

            with db.transaction():
                validate_workbook_data(load_batch_id, dataframes, error_repo=error_repo)
                initial_errors = count_errors(load_batch_id)
                update_error_count(load_batch_id)

                if initial_errors > 0:
                    update_status(load_batch_id, BatchStatus.FAILED)
                    logger.warning(
                        "Workbook validation failed load_batch_id=%s source_file=%s error_count=%s",
                        load_batch_id,
                        source_file_name,
                        initial_errors,
                        extra=_batch_extra(
                            load_batch_id,
                            source_file_name=source_file_name,
                            error_count=initial_errors,
                            status=BatchStatus.FAILED.value,
                        ),
                    )
                    return IngestionResult(
                        load_batch_id=load_batch_id,
                        status=BatchStatus.FAILED,
                        error_count=initial_errors,
                        source_file_name=source_file_name,
                        content_hash=content_hash,
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
                logger.info(
                    "Staging complete load_batch_id=%s source_file=%s",
                    load_batch_id,
                    source_file_name,
                    extra=_batch_extra(
                        load_batch_id,
                        source_file_name=source_file_name,
                        status=BatchStatus.STAGED.value,
                    ),
                )
                sql_validate(load_batch_id)
                sql_commit(load_batch_id)

                final_errors = count_errors(load_batch_id)
                update_error_count(load_batch_id)

                if final_errors > 0:
                    update_status(load_batch_id, BatchStatus.FAILED)
                    logger.warning(
                        "SQL validation/commit failed load_batch_id=%s source_file=%s error_count=%s",
                        load_batch_id,
                        source_file_name,
                        final_errors,
                        extra=_batch_extra(
                            load_batch_id,
                            source_file_name=source_file_name,
                            error_count=final_errors,
                            status=BatchStatus.FAILED.value,
                        ),
                    )
                    return IngestionResult(
                        load_batch_id=load_batch_id,
                        status=BatchStatus.FAILED,
                        error_count=final_errors,
                        source_file_name=source_file_name,
                        content_hash=content_hash,
                    )

                update_status(load_batch_id, BatchStatus.COMMITTED)

            logger.info(
                "Ingestion committed load_batch_id=%s source_file=%s",
                load_batch_id,
                source_file_name,
                extra=_batch_extra(
                    load_batch_id,
                    source_file_name=source_file_name,
                    status=BatchStatus.COMMITTED.value,
                    error_count=0,
                ),
            )
            return IngestionResult(
                load_batch_id=load_batch_id,
                status=BatchStatus.COMMITTED,
                error_count=0,
                source_file_name=source_file_name,
                content_hash=content_hash,
            )

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            # Full traceback goes to logs only — never into stg.ValidationError.
            logger.exception(
                "Ingestion exception load_batch_id=%s source_file=%s error=%s",
                load_batch_id,
                source_file_name,
                error_message,
                extra=_batch_extra(
                    load_batch_id,
                    source_file_name=source_file_name,
                    status=BatchStatus.FAILED.value,
                ),
            )
            db.rollback()
            try:
                log_error(
                    load_batch_id=load_batch_id,
                    sheet_name=None,
                    row_num=None,
                    column_name=None,
                    error_type=ErrorType.EXCEPTION.value,
                    error_message=error_message[:1000],
                    severity=Severity.ERROR.value,
                    use_row_data_column=True,
                )
                update_error_count(load_batch_id)
                update_status(load_batch_id, BatchStatus.FAILED)
                db.commit()
            except Exception:
                logger.exception(
                    "Could not persist ingestion exception load_batch_id=%s",
                    load_batch_id,
                    extra=_batch_extra(load_batch_id),
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
                content_hash=content_hash,
            )
        finally:
            db.close()
