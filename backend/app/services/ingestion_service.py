"""
This service is responsible for ingesting Excel files into the database.
It uses the ingestion_engine library to process the files.
it contains the business logic for handling excel file uploads, batch tracking, error reporting etc.
it does not define routes,instead it provides functions that the routes can call.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ingestion_engine import excel_file_ingestion as ingestion
from ingestion_engine.pipeline import IngestionPipeline


def run_ingestion_from_path(input_path: str) -> dict:
    return ingestion.process_local_file(input_path).as_dict()


async def run_ingestion_from_upload(upload: UploadFile) -> dict:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    if not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx uploads are supported.")

    from backend.app.core.settings import get_settings

    max_bytes = max(1, int(get_settings().upload_max_bytes))
    content_length = upload.headers.get("content-length") if upload.headers else None
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds maximum size of {max_bytes} bytes.",
                )
        except ValueError:
            pass

    file_bytes = await upload.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum size of {max_bytes} bytes.",
        )

    pipeline = IngestionPipeline(
        connection_factory=ingestion.get_connection,
        insert_rows=ingestion.insert_dataframe_rows,
        get_decimal_metadata=ingestion._get_decimal_metadata,
        resolve_sector_code=ingestion.resolve_sector_code,
        fetch_all=ingestion.fetch_all,
        log_validation_error=ingestion.log_validation_error,
        create_load_batch=ingestion.create_load_batch,
        update_batch_status=ingestion.update_batch_status,
        update_batch_error_count=ingestion.update_batch_error_count,
        get_error_count=ingestion.get_error_count,
        run_sql_validation=ingestion.run_sql_validation,
        run_sql_commit=ingestion.run_sql_commit,
    )

    def _run():
        import io

        return pipeline.run(
            io.BytesIO(file_bytes),
            upload.filename,
            f"upload://{upload.filename}",
        ).as_dict()

    return await run_in_threadpool(_run)


def get_batch_summary(load_batch_id: str) -> dict:
    summary = ingestion.get_batch_summary(load_batch_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Load batch not found.")
    return summary


def get_batch_error_counts(load_batch_id: str) -> list[dict]:
    return ingestion.get_batch_error_counts(load_batch_id)


def get_batch_error_details(load_batch_id: str) -> list[dict]:
    details = ingestion.get_batch_error_details(load_batch_id)
    cleaned: list[dict] = []
    for row in details:
        updated = dict(row)
        updated.pop("RowDataJson", None)
        cleaned.append(updated)
    return cleaned


def _coerce_sql_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _table_name_for_sheet(sheet_name: str | None) -> str | None:
    mapping = {
        "ProjectInformation": "stg.ProjectInformation",
        "ProjectQuants": "stg.ProjectQuants",
        "ElementQuants_L2": "stg.ElementQuants_L2",
        "Level2": "stg.Level2",
        "LineItem_L3": "stg.LineItem_L3",
        "Adjustments": "stg.Adjustments",
    }
    return mapping.get(sheet_name or "")


def _parse_row_data_json(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def get_batch_error_rows(load_batch_id: str) -> list[dict]:
    details = ingestion.get_batch_error_details(load_batch_id)
    rows_with_data: list[dict] = []

    for detail in details:
        sheet_name = detail.get("SheetName")
        row_num = detail.get("RowNum")
        table_name = _table_name_for_sheet(sheet_name)
        row_data = _parse_row_data_json(detail.get("RowDataJson"))

        if row_data is None and table_name and row_num is not None:
            sql = f"""
                SELECT TOP 1 *
                FROM {table_name}
                WHERE LoadBatchID = ?
                  AND RowNum = ?
            """
            matches = ingestion.fetch_all(sql, (load_batch_id, row_num))
            if matches:
                raw_row = matches[0]
                row_data = {
                    key: _coerce_sql_value(value)
                    for key, value in raw_row.items()
                    if key not in {"LoadBatchID", "SourceFileName"}
                    and not key.lower().startswith("stage")
                }

        merged = dict(detail)
        merged.pop("RowDataJson", None)
        merged["RowData"] = row_data
        rows_with_data.append(merged)

    return rows_with_data


def build_batch_error_csv(load_batch_id: str) -> io.StringIO:
    details = get_batch_error_details(load_batch_id)

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "Severity",
            "SheetName",
            "RowNum",
            "ColumnName",
            "ErrorType",
            "ErrorMessage",
        ],
    )
    writer.writeheader()
    for row in details:
        writer.writerow({k: row.get(k) for k in writer.fieldnames})

    buffer.seek(0)
    return buffer
