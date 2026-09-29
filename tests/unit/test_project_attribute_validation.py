"""Project attribute validation: blank values pass, non-blank values outside the domain fail."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ingestion_engine.project_attributes import (
    VALIDATED_FIELDS,
    canonical_choice,
    is_blank,
)
from ingestion_engine.staging.stagers import ProjectInformationStager
from ingestion_engine.validation.report import ProjectAttributeValidator, ValidationReport

BLANKS = [None, float("nan"), "", "   "]


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


def _validate(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    row = {"ProjectID": "P1", "ProjectName": "Demo", **attributes}
    repo = FakeErrorRepo()
    ProjectAttributeValidator().validate(
        "batch-1",
        {"ProjectInformation": pd.DataFrame([row])},
        error_repo=repo,
        report=ValidationReport(),
    )
    return repo.calls


@pytest.mark.parametrize("value", BLANKS, ids=["none", "nan", "empty", "whitespace"])
def test_is_blank_true_for_empty_inputs(value):
    assert is_blank(value)


@pytest.mark.parametrize("value", [0, 0.0, False, "0", "x"], ids=repr)
def test_is_blank_false_for_values_including_zero(value):
    assert not is_blank(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Medium", "Medium"), (" medium ", "Medium"), ("HIGH", "High"), ("Premium", None)],
)
def test_canonical_choice(value, expected):
    assert canonical_choice(value, ("Low", "Medium", "High")) == expected


def test_missing_columns_produce_no_errors():
    assert _validate({}) == []


@pytest.mark.parametrize("field", VALIDATED_FIELDS)
@pytest.mark.parametrize("value", BLANKS, ids=["none", "nan", "empty", "whitespace"])
def test_blank_value_produces_no_error(field, value):
    assert _validate({field: value}) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("SpecLevel", "Medium"),
        ("SpecLevel", " medium "),
        ("SpecLevel", "HIGH"),
        ("SiteType", "brownfield"),
        ("SiteType", "Greenfield"),
        ("ComplexityRating", 1),
        ("ComplexityRating", 5),
        ("ComplexityRating", 3.0),
        ("ComplexityRating", "3"),
        ("NrOfStoreys", 0),
        ("NrOfStoreys", 12),
        ("TotalHeightGroundToRoof", 13.5),
        ("BasementArea", 0),
        ("BasementHeight", "3.25"),
    ],
)
def test_valid_value_produces_no_error(field, value):
    assert _validate({field: value}) == []


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("SpecLevel", "Premium", "DOMAIN"),
        ("SiteType", "Urban", "DOMAIN"),
        ("ComplexityRating", 0, "DOMAIN"),
        ("ComplexityRating", 6, "DOMAIN"),
        ("ComplexityRating", 3.5, "DOMAIN"),
        ("ComplexityRating", "Medium", "DOMAIN"),
        ("ComplexityRating", "abc", "DOMAIN"),
        ("NrOfStoreys", -1, "INVALID_NUMBER"),
        ("NrOfStoreys", 2.5, "INVALID_NUMBER"),
        ("TotalHeightGroundToRoof", -3, "INVALID_NUMBER"),
        ("BasementArea", "large", "INVALID_NUMBER"),
        ("BasementHeight", True, "INVALID_NUMBER"),
    ],
)
def test_non_blank_invalid_value_produces_one_error(field, value, error_type):
    calls = _validate({field: value})
    assert len(calls) == 1
    call = calls[0]
    assert call["column_name"] == field
    assert call["error_type"] == error_type
    assert str(value) in call["error_message"]


def test_blank_field_next_to_invalid_field_reports_only_the_invalid_one():
    calls = _validate({"SpecLevel": "   ", "SiteType": "Urban", "ComplexityRating": None})
    assert [c["column_name"] for c in calls] == ["SiteType"]


def _stage(attributes: dict[str, Any]) -> dict[str, Any]:
    stager = ProjectInformationStager(connection_factory=MagicMock)
    row = {"ProjectID": "P1", "ProjectName": "Demo", **attributes}
    return stager.build_rows("batch-1", "demo.xlsx", pd.DataFrame([row]))[0]


def test_stager_canonicalises_choices_and_coerces_complexity():
    staged = _stage({"SpecLevel": " medium", "SiteType": "BROWNFIELD", "ComplexityRating": 3.0})
    assert staged["SpecLevel"] == "Medium"
    assert staged["SiteType"] == "Brownfield"
    assert staged["ComplexityRating"] == 3


def test_stager_stages_blank_choices_as_null():
    staged = _stage({"SpecLevel": "", "SiteType": None})
    assert staged["SpecLevel"] is None
    assert staged["SiteType"] is None


def test_stager_raises_on_unvalidated_choice():
    with pytest.raises(ValueError, match="SpecLevel"):
        _stage({"SpecLevel": "Premium"})
