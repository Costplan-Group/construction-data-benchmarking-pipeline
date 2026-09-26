"""Unit tests for simple sheet normalizers, contractor, and summary header detection."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from ingestion_engine.contractor import ContractorSelector
from ingestion_engine.workbook.normalizers.adjustments import AdjustmentsNormalizer
from ingestion_engine.workbook.normalizers.element_quants import ElementQuantsNormalizer
from ingestion_engine.workbook.normalizers.project_information import (
    ProjectInformationNormalizer,
    extract_tenderers_from_project_information_df,
    is_placeholder_tenderer_name,
)
from ingestion_engine.workbook.normalizers.project_quants import (
    ProjectQuantsNormalizer,
    extract_gifa_from_project_quants,
)
from ingestion_engine.workbook.normalizers.summary_header import (
    detect_contractor_metric_blocks,
    detect_summary_column_indices,
    detect_summary_header_row,
)


def test_project_information_key_value_layout():
    raw = pd.DataFrame(
        {
            "Field": ["Project ID", "Project Name", "Sector", "Contractor 1"],
            "Value": ["P99", "Tower", "Office", "Alpha Ltd"],
        }
    )
    out = ProjectInformationNormalizer().normalize(raw)
    assert list(out.columns) >= []
    row = out.iloc[0]
    assert row["ProjectID"] == "P99"
    assert row["ProjectName"] == "Tower"
    assert row["SectorCode"] == "Office"
    assert row["Contractor 1"] == "Alpha Ltd"


def test_project_information_wide_rename():
    raw = pd.DataFrame(
        [{"Project Number": "P1", "ProjectName": "A", "Selected Contractor": "Beta"}]
    )
    out = ProjectInformationNormalizer().normalize(raw)
    assert "ProjectID" in out.columns
    assert out.iloc[0]["SelectedContractor"] == "Beta"


def test_placeholder_and_tenderer_extract():
    assert is_placeholder_tenderer_name("") is True
    assert is_placeholder_tenderer_name("TBD") is True
    assert is_placeholder_tenderer_name("Insert Contractor Name") is True
    assert is_placeholder_tenderer_name("Alpha") is False

    df = pd.DataFrame([{"Contractor 1": "Alpha", "Contractor 2": "TBD", "Contractor 3": "Beta"}])
    tenderers = extract_tenderers_from_project_information_df(df)
    assert tenderers == [("Contractor 1", "Alpha"), ("Contractor 3", "Beta")]


def test_project_quants_rename_and_gifa():
    raw = pd.DataFrame(
        [
            {"Code": "PQ-1", "Name": "GIFA", "Quantity": "1250.5", "UOM": "m2"},
            {"Code": "PQ-2", "Name": "Other", "Quantity": "10", "UOM": "nr"},
        ]
    )
    out = ProjectQuantsNormalizer().normalize(raw)
    assert "ProjectQuantCode" in out.columns
    assert "Qty" in out.columns
    assert extract_gifa_from_project_quants(out) == Decimal("1250.5")


def test_project_quants_generates_code_when_missing():
    raw = pd.DataFrame([{"Name": "GIFA", "Qty": 1, "Unit": "m2"}])
    out = ProjectQuantsNormalizer().normalize(raw)
    assert out.iloc[0]["ProjectQuantCode"] == "PQ-001"


def test_element_quants_rename_and_defaults():
    raw = pd.DataFrame([{"Code": "1.10", "Element": "Substructure", "Quantity": 5, "Unit": "m2"}])
    out = ElementQuantsNormalizer().normalize(raw)
    assert out.iloc[0]["L2Code"] == "1.1"
    assert out.iloc[0]["QuantTypeCode"] == "DEFAULT"


def test_element_quants_embedded_header():
    raw = pd.DataFrame(
        [
            [None, None, None, None],
            ["Code", "Element", "Qty", "Unit"],
            ["2.1", "Frame", 3, "m2"],
        ]
    )
    out = ElementQuantsNormalizer().normalize(raw)
    assert "L2Code" in out.columns
    assert out.iloc[0]["L2Code"] == "2.1"


def test_adjustments_rename():
    raw = pd.DataFrame([{"Category": "Contingency", "Value": 100, "Percent": 5, "Method": "pct"}])
    out = AdjustmentsNormalizer().normalize(raw)
    assert set(out.columns) >= {"AdjCategory", "Amount", "RatePercent", "Method"}


def test_contractor_selector_basic():
    selector = ContractorSelector()
    pi = pd.DataFrame([{"SelectedContractor": "Alpha"}])
    assert selector.get_selected_contractor(pi) == "Alpha"

    banner = pd.DataFrame([["Selected contractor: Beta Ltd", None]])
    assert selector.detect_from_sheet_row(banner) == "Beta Ltd"

    metrics = pd.DataFrame(
        [{"Alpha Qty": 1, "Alpha Unit": "m2", "Alpha Rate": 2, "Alpha Total": 2}]
    )
    assert selector.resolve_metric_column(metrics, ["Qty", "Quantity"], "Alpha") == "Alpha Qty"

    assert ContractorSelector.forward_fill_header_labels(["A", None, "B", None]) == [
        "A",
        "A",
        "B",
        "B",
    ]


def test_summary_header_detection():
    raw = pd.DataFrame(
        [
            ["noise", "noise", "noise", "noise", "noise", "noise"],
            ["Ref", "Element", "Rate", "Total", "Rate", "Total"],
            ["1.0", "Substructure", 10, 100, 11, 110],
            ["1.1", "Excavation", 10, 100, 11, 110],
        ]
    )
    header_idx = detect_summary_header_row(raw)
    assert header_idx == 1
    ref, name, rate, total = detect_summary_column_indices(raw.iloc[header_idx].tolist())
    assert (ref, name, rate, total) == (0, 1, 2, 3)
    metric_idx, blocks = detect_contractor_metric_blocks(raw, header_idx)
    assert metric_idx == 1
    assert blocks == [(2, 3), (4, 5)]
