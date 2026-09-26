"""Unit tests for AI SQL guard (no database)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.services.ai_sql_guard import guard_ai_sql, is_allowed_warehouse_table


def test_warehouse_table_allowlist():
    assert is_allowed_warehouse_table("dbo", "DimProject")
    assert is_allowed_warehouse_table("dbo", "FactElementCostL2")
    assert is_allowed_warehouse_table("dbo", "factLineItem_L3")
    assert not is_allowed_warehouse_table("stg", "ProjectInformation")
    assert not is_allowed_warehouse_table("dbo", "vw_BI_ProjectOverview")
    assert not is_allowed_warehouse_table("sys", "objects")


def test_rejects_select_into():
    with pytest.raises(HTTPException) as exc:
        guard_ai_sql(
            "SELECT * INTO dbo.NewTable FROM dbo.DimProject",
            max_rows=500,
        )
    assert exc.value.status_code == 400
    assert "INTO" in str(exc.value.detail).upper()


def test_rejects_sys_objects():
    with pytest.raises(HTTPException) as exc:
        guard_ai_sql("SELECT name FROM sys.objects", max_rows=500)
    assert exc.value.status_code == 400


def test_rejects_staging_table():
    with pytest.raises(HTTPException) as exc:
        guard_ai_sql("SELECT * FROM stg.LoadBatch", max_rows=500)
    assert exc.value.status_code == 400


def test_rejects_bi_views():
    with pytest.raises(HTTPException) as exc:
        guard_ai_sql("SELECT * FROM dbo.vw_BI_ProjectOverview", max_rows=500)
    assert exc.value.status_code == 400


def test_rejects_openrowset():
    with pytest.raises(HTTPException) as exc:
        guard_ai_sql("SELECT * FROM OPENROWSET('SQLOLEDB', 'x')", max_rows=500)
    assert exc.value.status_code == 400


def test_rejects_multi_statement():
    with pytest.raises(HTTPException) as exc:
        guard_ai_sql(
            "SELECT ProjectID FROM dbo.DimProject; SELECT ProjectID FROM dbo.DimCostSet",
            max_rows=500,
        )
    assert exc.value.status_code == 400
    assert "single" in str(exc.value.detail).lower()


def test_accepts_cte_and_injects_top():
    result = guard_ai_sql(
        """
        WITH ranked AS (
            SELECT L2Name, TotalCost
            FROM dbo.DimElementL2 e
            JOIN dbo.FactElementCostL2 f ON f.elementL2Key = e.ElementL2Key
        )
        SELECT L2Name, TotalCost FROM ranked ORDER BY TotalCost DESC
        """,
        max_rows=500,
    )
    assert "TOP 500" in result.sql.upper()
    assert result.truncated is True


def test_accepts_join_across_dim_fact():
    result = guard_ai_sql(
        """
        SELECT p.ProjectName, s.SectorName
        FROM dbo.DimProject AS p
        JOIN dbo.DimSector AS s
          ON p.SectorKey = s.SectorKey
        """,
        max_rows=500,
    )
    assert "DimProject" in result.sql
    assert "DimSector" in result.sql
    assert "TOP 500" in result.sql.upper()


def test_accepts_literal_containing_update():
    result = guard_ai_sql(
        "SELECT ProjectName FROM dbo.DimProject WHERE ProjectName = 'Update Road'",
        max_rows=500,
    )
    assert "Update Road" in result.sql
    assert result.truncated is True


def test_accepts_and_or_in_where():
    result = guard_ai_sql(
        """
        SELECT p.ProjectName, f.TotalCost
        FROM dbo.DimProject p
        JOIN dbo.DimCostSet cs ON cs.ProjectKey = p.ProjectKey
        JOIN dbo.FactElementCostL2 f ON f.costSetKey = cs.CostSetKey
        WHERE p.ProjectName LIKE '%hospital%' AND f.TotalCost > 0
        ORDER BY f.TotalCost DESC
        """,
        max_rows=500,
    )
    assert "AND" in result.sql.upper()
    assert "DimProject" in result.sql


def test_accepts_case_expression():
    result = guard_ai_sql(
        """
        SELECT
            ProjectName,
            CASE WHEN SectorKey IS NULL THEN 'Unknown' ELSE 'Known' END AS SectorFlag
        FROM dbo.DimProject
        """,
        max_rows=500,
    )
    assert "CASE" in result.sql.upper()
    assert "DimProject" in result.sql


def test_preserves_smaller_top():
    result = guard_ai_sql(
        "SELECT TOP 10 ProjectName FROM dbo.DimProject",
        max_rows=500,
    )
    assert "TOP 10" in result.sql.upper()
    assert result.truncated is False


def test_caps_excessive_top():
    result = guard_ai_sql(
        "SELECT TOP 9999 ProjectName FROM dbo.DimProject",
        max_rows=500,
    )
    assert "TOP 500" in result.sql.upper()
    assert result.truncated is True
