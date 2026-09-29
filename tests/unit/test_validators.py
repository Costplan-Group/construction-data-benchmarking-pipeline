"""Unit tests for workbook validators (no database)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from ingestion_engine.validation.report import (
    RequiredColumnsValidator,
    RowLevelValidator,
    ValidationReport,
    validate_workbook_data,
)


class FakeErrorRepo:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def log(self, *args: Any, **kwargs: Any) -> None:
        payload = dict(kwargs)
        if args:
            payload["load_batch_id"] = args[0]
            if len(args) > 1:
                payload["sheet_name"] = args[1]
        self.calls.append(payload)


def _minimal_ok_frames() -> dict[str, pd.DataFrame]:
    return {
        "ProjectInformation": pd.DataFrame(
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
        ),
        "ProjectQuants": pd.DataFrame([{"ProjectQuantName": "GIFA", "Qty": 100, "Unit": "m2"}]),
        "ElementQuants_L2": pd.DataFrame(
            [{"L2Code": "1.1", "QuantTypeCode": "DEFAULT", "Qty": 10}]
        ),
        "Level2": pd.DataFrame([{"L2Code": "1.1", "L2Name": "Substructure", "TotalCost": 1000}]),
        "LineItem_L3": pd.DataFrame(
            [
                {
                    "L2Code": "1.1",
                    "ItemDescription": "Excavate",
                    "RowType": "ITEM",
                }
            ]
        ),
        "Adjustments": pd.DataFrame([{"AdjCategory": "Contingency", "Amount": 50}]),
    }


def test_required_columns_logs_missing():
    repo = FakeErrorRepo()
    report = ValidationReport()
    frames = _minimal_ok_frames()
    frames["ProjectQuants"] = pd.DataFrame([{"ProjectQuantName": "GIFA"}])  # missing Qty/Unit

    RequiredColumnsValidator().validate("batch-1", frames, error_repo=repo, report=report)

    missing = [c for c in repo.calls if c.get("error_type") == "MISSING_COLUMN"]
    assert {c["column_name"] for c in missing} == {"Qty", "Unit"}
    assert "RequiredColumnsValidator" in report.ran_validators


def test_row_level_pi_count_invalid_number_and_rowtype():
    repo = FakeErrorRepo()
    report = ValidationReport()
    frames = _minimal_ok_frames()
    frames["ProjectInformation"] = pd.concat(
        [frames["ProjectInformation"], frames["ProjectInformation"]],
        ignore_index=True,
    )
    frames["Level2"] = pd.DataFrame([{"L2Code": "1.1", "L2Name": "X", "TotalCost": "not-a-number"}])
    frames["LineItem_L3"] = pd.DataFrame(
        [{"L2Code": "1.1", "ItemDescription": "X", "RowType": "WEIRD"}]
    )
    frames["ProjectQuants"] = pd.DataFrame(
        [{"ProjectQuantName": "GIFA", "Qty": "abc", "Unit": "m2"}]
    )

    RowLevelValidator().validate("batch-1", frames, error_repo=repo, report=report)

    types = {c.get("error_type") for c in repo.calls}
    assert "ROW_COUNT" in types
    assert "INVALID_NUMBER" in types
    assert "DOMAIN" in types


def test_validate_workbook_data_orchestrator_and_log_fn_adapter():
    frames = _minimal_ok_frames()
    report = validate_workbook_data("batch-1", frames, error_repo=FakeErrorRepo())
    assert report.ran_validators == [
        "RequiredColumnsValidator",
        "RowLevelValidator",
        "ProjectAttributeValidator",
    ]

    logged: list[tuple] = []

    def log_fn(load_batch_id, sheet_name=None, **kwargs):
        logged.append((load_batch_id, sheet_name, kwargs))

    bad = _minimal_ok_frames()
    bad["ProjectQuants"] = pd.DataFrame([{"ProjectQuantName": "GIFA"}])
    validate_workbook_data("batch-2", bad, log_fn=log_fn)
    assert logged


def test_validate_workbook_data_requires_repo_or_log_fn():
    with pytest.raises(ValueError, match="error_repo or log_fn"):
        validate_workbook_data("batch-1", _minimal_ok_frames())
