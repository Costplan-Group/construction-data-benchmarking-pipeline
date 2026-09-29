"""End-to-end ingestion against SQL Server in Docker."""

from __future__ import annotations

from decimal import Decimal
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


def _scalar(conn, sql: str, params=None):
    cur = conn.cursor()
    if params is not None:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    row = cur.fetchone()
    return row[0] if row else None


def test_commit_populates_warehouse_dims_and_facts(db_connection):
    result = process_local_file(str(SAMPLE_WORKBOOK))
    assert result.status == BatchStatus.COMMITTED, result.exception
    batch_id = result.load_batch_id

    cost_set_lookup = """
        SELECT cs.CostSetKey
        FROM dbo.DimCostSet cs
        INNER JOIN stg.ProjectInformation pi
            ON pi.ProjectID = cs.ProjectID
           AND (cs.CostStage = NULLIF(LTRIM(RTRIM(pi.CostStage)), '')
                OR (cs.CostStage IS NULL AND NULLIF(LTRIM(RTRIM(pi.CostStage)), '') IS NULL))
        WHERE pi.LoadBatchID = ?
    """
    natural_key_rows = """
        SELECT COUNT(*)
        FROM dbo.DimCostSet cs
        INNER JOIN dbo.DimCostSet ref
            ON ref.CostSetKey = ?
        WHERE cs.ProjectID = ref.ProjectID
          AND (cs.ContractorKey = ref.ContractorKey
               OR (cs.ContractorKey IS NULL AND ref.ContractorKey IS NULL))
          AND (cs.CostStage = ref.CostStage
               OR (cs.CostStage IS NULL AND ref.CostStage IS NULL))
    """

    cost_set_key = _scalar(db_connection, cost_set_lookup, (batch_id,))
    assert cost_set_key is not None
    assert _count(db_connection, natural_key_rows, (cost_set_key,)) == 1

    staged_l2_codes = _count(
        db_connection,
        """
        SELECT COUNT(DISTINCT UPPER(LTRIM(RTRIM(L2Code))))
        FROM stg.Level2
        WHERE LoadBatchID = ? AND NULLIF(LTRIM(RTRIM(L2Code)), '') IS NOT NULL
        """,
        (batch_id,),
    )
    staged_total = _scalar(
        db_connection,
        "SELECT SUM(TotalCost) FROM stg.Level2 WHERE LoadBatchID = ?",
        (batch_id,),
    )
    assert staged_l2_codes > 0

    fact_rows = _count(
        db_connection,
        "SELECT COUNT(*) FROM dbo.FactElementCostL2 WHERE costSetKey = ?",
        (cost_set_key,),
    )
    fact_total = _scalar(
        db_connection,
        "SELECT SUM(TotalCost) FROM dbo.FactElementCostL2 WHERE costSetKey = ?",
        (cost_set_key,),
    )
    assert fact_rows == staged_l2_codes
    assert fact_total == staged_total

    missing_elements = _count(
        db_connection,
        """
        SELECT COUNT(*)
        FROM stg.Level2 l2
        WHERE l2.LoadBatchID = ?
          AND NOT EXISTS (
              SELECT 1 FROM dbo.DimElementL2 e
              WHERE UPPER(LTRIM(RTRIM(e.L2Code))) = UPPER(LTRIM(RTRIM(l2.L2Code)))
          )
        """,
        (batch_id,),
    )
    assert missing_elements == 0

    missing_contractors = _count(
        db_connection,
        """
        SELECT COUNT(*)
        FROM stg.ProjectTenderer pt
        WHERE pt.LoadBatchID = ?
          AND NOT EXISTS (
              SELECT 1 FROM dbo.DimContractor dc
              WHERE UPPER(LTRIM(RTRIM(dc.ContractorName)))
                  = UPPER(LTRIM(RTRIM(COALESCE(NULLIF(LTRIM(RTRIM(pt.TendererName)), ''), pt.TendererLabel))))
          )
        """,
        (batch_id,),
    )
    assert missing_contractors == 0

    has_selected = _count(
        db_connection,
        "SELECT COUNT(*) FROM stg.ProjectTenderer WHERE LoadBatchID = ? AND IsSelected = 1",
        (batch_id,),
    )
    contractor_key = _scalar(
        db_connection,
        "SELECT ContractorKey FROM dbo.DimCostSet WHERE CostSetKey = ?",
        (cost_set_key,),
    )
    if has_selected:
        assert contractor_key is not None

    project = db_connection.cursor()
    project.execute(
        """
        SELECT dp.SpecLevel, dp.SiteType, dp.NrOfStoreys, dp.TotalHeightGroundToRoof,
               dp.BasementArea, dp.BasementHeight, dp.ComplexityRating,
               dp.AccessConstraints, dp.Occupied
        FROM dbo.DimProject dp
        INNER JOIN stg.ProjectInformation pi
            ON pi.ProjectID = dp.ProjectID
        WHERE pi.LoadBatchID = ?
        """,
        (batch_id,),
    )
    project_row = project.fetchone()
    assert project_row is not None
    assert tuple(project_row) == (
        "Medium",
        "Brownfield",
        3,
        Decimal("13.50"),
        Decimal("0.00"),
        Decimal("0.00"),
        "Medium",
        "Restricted - live campus",
        True,
    )

    summary = db_connection.cursor()
    summary.execute(
        """
        SELECT measuredWorksTotal, grandTotal
        FROM dbo.FactCostSetSummary
        WHERE costSetKey = ?
        """,
        (cost_set_key,),
    )
    summary_row = summary.fetchone()
    assert summary_row is not None
    assert summary_row[0] == staged_total
    assert summary_row[1] is not None

    # Re-committing upserts the same DimCostSet row and replaces its facts.
    cur = db_connection.cursor()
    cur.execute("EXEC stg.usp_CommitBatch ?", (batch_id,))
    db_connection.commit()
    assert _scalar(db_connection, cost_set_lookup, (batch_id,)) == cost_set_key
    assert _count(db_connection, natural_key_rows, (cost_set_key,)) == 1
    assert (
        _count(
            db_connection,
            "SELECT COUNT(*) FROM dbo.FactElementCostL2 WHERE costSetKey = ?",
            (cost_set_key,),
        )
        == staged_l2_codes
    )


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
