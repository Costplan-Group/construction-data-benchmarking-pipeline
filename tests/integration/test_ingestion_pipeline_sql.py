"""End-to-end ingestion against SQL Server in Docker."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion_engine.enums import BatchStatus
from ingestion_engine.excel_file_ingestion import process_local_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_WORKBOOK = REPO_ROOT / "sample_data" / "DEMO_Tender_Comparison_Workbook.xlsx"
FAILING_WORKBOOK = REPO_ROOT / "sample_data" / "DEMO_Failing_Workbook.xlsx"

# Staging row counts for DEMO_Tender_Comparison_Workbook (characterization goldens).
EXPECTED_STAGING_COUNTS = {
    "stg.ProjectInformation": 1,
    "stg.ProjectTenderer": 3,
    "stg.ProjectQuants": 4,
    "stg.ElementQuants_L2": 6,
    "stg.Level2": 6,
    "stg.LineItem_L3": 9,
}


pytestmark = pytest.mark.integration


def _count(conn, sql: str, params=None) -> int:
    cur = conn.cursor()
    if params is not None:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def test_sample_workbook_commits_with_expected_staging_counts(db_connection):
    assert SAMPLE_WORKBOOK.exists(), f"Missing sample workbook: {SAMPLE_WORKBOOK}"

    result = process_local_file(str(SAMPLE_WORKBOOK))

    assert result.status == BatchStatus.COMMITTED, (
        f"expected COMMITTED, got {result.status}; "
        f"error_count={result.error_count}; exception={result.exception}"
    )
    assert result.error_count == 0
    assert result.load_batch_id

    cur = db_connection.cursor()
    cur.execute(
        "SELECT BatchStatus, ErrorCount FROM stg.LoadBatch WHERE LoadBatchID = ?",
        (result.load_batch_id,),
    )
    row = cur.fetchone()
    assert row is not None
    batch_status, error_count = row[0], row[1]
    assert batch_status == BatchStatus.COMMITTED.value
    assert int(error_count or 0) == 0

    for table, expected in EXPECTED_STAGING_COUNTS.items():
        actual = _count(
            db_connection,
            f"SELECT COUNT(*) FROM {table} WHERE LoadBatchID = ?",
            (result.load_batch_id,),
        )
        assert actual == expected, f"{table}: expected {expected}, got {actual}"

    validation_errors = _count(
        db_connection,
        """
        SELECT COUNT(*)
        FROM stg.ValidationError
        WHERE LoadBatchID = ?
          AND Severity = 'ERROR'
        """,
        (result.load_batch_id,),
    )
    assert validation_errors == 0


def test_failing_workbook_marks_batch_failed(db_connection):
    assert FAILING_WORKBOOK.exists(), f"Missing failing workbook: {FAILING_WORKBOOK}"

    result = process_local_file(str(FAILING_WORKBOOK))

    assert result.status == BatchStatus.FAILED
    assert result.error_count >= 1
    assert result.load_batch_id

    cur = db_connection.cursor()
    cur.execute(
        "SELECT BatchStatus FROM stg.LoadBatch WHERE LoadBatchID = ?",
        (result.load_batch_id,),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == BatchStatus.FAILED.value

    error_rows = _count(
        db_connection,
        """
        SELECT COUNT(*)
        FROM stg.ValidationError
        WHERE LoadBatchID = ?
          AND Severity = 'ERROR'
        """,
        (result.load_batch_id,),
    )
    assert error_rows >= 1
