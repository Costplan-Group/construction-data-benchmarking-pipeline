"""Unit tests for staging mappers with no live database."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ingestion_engine.staging.stagers import (
    AdjustmentsStager,
    ElementQuantsL2Stager,
    Level2Stager,
    LineItemL3Stager,
    ProjectInformationStager,
    ProjectQuantsStager,
    ProjectTendererStager,
)


def test_project_information_stager_build_rows():
    stager = ProjectInformationStager(
        connection_factory=MagicMock,
        resolve_sector_code=lambda v: "OFF" if v else None,
    )
    df = pd.DataFrame(
        [
            {
                "ProjectID": "P1",
                "ProjectName": "Demo",
                "LocationLabel": "London",
                "SectorCode": "Office",
                "CostStage": "Tender",
                "SelectedContractor": "Alpha",
                "Demolition": "Yes",
                "NewBuild": 1,
                "GIFA": "100.5",
                "ProgrammeLengthInWeeks": "12",
            }
        ]
    )
    rows = stager.build_rows("batch-1", "demo.xlsx", df)
    assert len(rows) == 1
    row = rows[0]
    assert row["SectorCode"] == "OFF"
    assert row["Demolition"] == 1
    assert row["GIFA"] == Decimal("100.5")


def test_project_information_uses_fallback_gifa():
    stager = ProjectInformationStager(connection_factory=MagicMock)
    df = pd.DataFrame(
        [
            {
                "ProjectID": "P1",
                "ProjectName": "Demo",
                "LocationLabel": "London",
                "SectorCode": "OFF",
                "CostStage": "Tender",
                "SelectedContractor": "Alpha",
            }
        ]
    )
    rows = stager.build_rows("batch-1", "demo.xlsx", df, fallback_gifa=Decimal("77"))
    assert rows[0]["GIFA"] == Decimal("77")


def test_project_tenderer_stager_build_rows():
    stager = ProjectTendererStager(
        connection_factory=MagicMock,
        get_decimal_meta=lambda _t: {},
        fetch_all=lambda *_a, **_k: [{"COLUMN_NAME": "FinalAdjustedTenderSum"}],
    )
    df = pd.DataFrame(
        [{"SelectedContractor": "Alpha", "Contractor 1": "Alpha", "Contractor 2": "Beta"}]
    )
    df.attrs["summary_tenderer_totals"] = [
        {
            "TendererLabel": "Contractor 1",
            "FinalAdjustedTenderSum": Decimal("100"),
            "VarianceToBudget": Decimal("1"),
            "ConstructionBudget": Decimal("99"),
        }
    ]
    rows = stager.build_rows("batch-1", "demo.xlsx", df)
    assert len(rows) == 2
    selected = next(r for r in rows if r["TendererName"] == "Alpha")
    assert selected["IsSelected"] == 1


def test_project_quants_stager_build_rows():
    stager = ProjectQuantsStager(connection_factory=MagicMock)
    df = pd.DataFrame(
        [
            {
                "ProjectQuantCode": "PQ-1",
                "ProjectQuantName": "GIFA",
                "Qty": "10",
                "Unit": "m2",
            },
            {
                "ProjectQuantCode": None,
                "ProjectQuantName": None,
                "Qty": None,
                "Unit": None,
            },
        ]
    )
    rows = stager.build_rows("batch-1", "demo.xlsx", df)
    assert len(rows) == 1
    assert rows[0]["Qty"] == Decimal("10")


def test_element_quants_and_l3_and_adjustments_stagers():
    eq = ElementQuantsL2Stager(connection_factory=MagicMock)
    eq_rows = eq.build_rows(
        "b",
        "f.xlsx",
        pd.DataFrame([{"L2Code": "1.1", "QuantTypeCode": "DEFAULT", "Qty": "3"}]),
    )
    assert eq_rows[0]["Qty"] == Decimal("3")

    l3 = LineItemL3Stager(connection_factory=MagicMock)
    l3_rows = l3.build_rows(
        "b",
        "f.xlsx",
        pd.DataFrame(
            [
                {
                    "L2Code": "1.1",
                    "ItemDescription": "Dig",
                    "Quantity": 2,
                    "Unit": "m3",
                    "Rate": 5,
                    "TotalCost": 10,
                },
                {
                    "L2Code": "1.1",
                    "ItemDescription": "Heading",
                    "Quantity": None,
                    "Unit": None,
                    "Rate": None,
                    "TotalCost": None,
                },
            ]
        ),
    )
    assert [r["DisplayOrder"] for r in l3_rows] == [1, 2]
    assert l3_rows[0]["RowType"] == "ITEM"
    assert l3_rows[1]["RowType"] == "HEADING"

    adj = AdjustmentsStager(connection_factory=MagicMock)
    adj_rows = adj.build_rows(
        "b",
        "f.xlsx",
        pd.DataFrame(
            [
                {
                    "AdjCategory": "Contingency",
                    "Amount": "10",
                    "RatePercent": "5",
                    "AppliedToBase": "Yes",
                    "IncludedInComparison": 1,
                }
            ]
        ),
    )
    assert adj_rows[0]["Amount"] == Decimal("10")
    assert adj_rows[0]["AppliedToBase"] == 1


def test_level2_stager_build_rows():
    stager = Level2Stager(
        connection_factory=MagicMock,
        get_decimal_meta=lambda _t: {"Rate": (18, 2), "TotalCost": (18, 2)},
    )
    df = pd.DataFrame(
        [
            {
                "L1Code": "1.0",
                "L1Name": "Substructure",
                "L2Code": "1.1",
                "L2Name": "Excavate",
                "Rate": "5",
                "TotalCost": "50",
            }
        ]
    )
    rows = stager.build_rows("batch-1", "demo.xlsx", df)
    assert rows[0]["TotalCost"] == Decimal("50.00") or rows[0]["TotalCost"] == Decimal("50")


def test_level2_stager_skips_null_total_and_logs():
    logs: list[dict] = []

    def log_fn(**kwargs):
        logs.append(kwargs)

    stager = Level2Stager(
        connection_factory=MagicMock,
        get_decimal_meta=lambda _t: {},
        log_validation_error=log_fn,
    )
    df = pd.DataFrame(
        [
            {
                "L1Code": "1.0",
                "L1Name": "Substructure",
                "L2Code": "1.1",
                "L2Name": "Excavate",
                "Rate": "5",
                "TotalCost": None,
            }
        ]
    )
    assert stager.build_rows("batch-1", "demo.xlsx", df) == []
    assert logs and logs[0]["error_type"] == "MISSING_TOTALCOST_SKIPPED"


def test_level2_stager_precision_error():
    stager = Level2Stager(
        connection_factory=MagicMock,
        get_decimal_meta=lambda _t: {"TotalCost": (4, 2)},
        log_validation_error=lambda **_k: None,
    )
    df = pd.DataFrame(
        [
            {
                "L1Code": "1.0",
                "L1Name": "Substructure",
                "L2Code": "1.1",
                "L2Name": "Excavate",
                "Rate": None,
                "TotalCost": "99999.99",
            }
        ]
    )
    with pytest.raises(ValueError, match="decimal precision"):
        stager.build_rows("batch-1", "demo.xlsx", df)
