"""Unit tests for value coercion and related pure helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ingestion_engine.coercion import (
    clean_value,
    normalize_text,
    resolve_sector_code,
    to_bit,
    to_decimal,
    to_int,
    unescape_html_text,
)
from ingestion_engine.row_utils import infer_l3_row_type, is_effectively_blank_row
from ingestion_engine.staging.decimal_coerce import (
    coerce_decimal_to_precision_scale,
    decimal_fits_precision_scale,
)
from ingestion_engine.workbook.aliases import (
    all_base_sheet_names_and_aliases,
    resolve_sheet_name,
    source_sheet_name,
    workbook_sheet_lookup,
)
from ingestion_engine.workbook.code_utils import format_code_text, split_l1_l2_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        (float("nan"), None),
        ("", None),
        ("  ", None),
        ("  hello  ", "hello"),
        (42, 42),
        (date(2024, 1, 2), date(2024, 1, 2)),
        (datetime(2024, 1, 2, 3, 4), datetime(2024, 1, 2, 3, 4)),
    ],
)
def test_clean_value(raw, expected):
    assert clean_value(raw) == expected


def test_clean_value_timestamp():
    ts = pd.Timestamp("2024-06-01 12:00:00")
    assert clean_value(ts) == ts.to_pydatetime()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("12", 12),
        ("12.9", 12),
        ("abc", None),
        (3.7, 3),
    ],
)
def test_to_int(raw, expected):
    assert to_int(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("1.25", Decimal("1.25")),
        (2, Decimal("2")),
        ("not-a-number", None),
    ],
)
def test_to_decimal(raw, expected):
    assert to_decimal(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        (True, 1),
        (False, 0),
        (1, 1),
        (0, 0),
        ("yes", 1),
        ("Y", 1),
        ("true", 1),
        ("no", 0),
        ("n", 0),
        ("maybe", None),
    ],
)
def test_to_bit(raw, expected):
    assert to_bit(raw) == expected


def test_unescape_html_text_double_encoded():
    assert unescape_html_text("&amp;amp;") == "&"
    assert unescape_html_text("A &amp; B") == "A & B"


def test_normalize_text():
    assert normalize_text(None) == ""
    assert normalize_text("  Hello-World!! ") == "helloworld"
    assert normalize_text("A &amp; B") == "ab"


def test_resolve_sector_code_none():
    assert resolve_sector_code(None, connection_factory=lambda: MagicMock()) is None


def test_resolve_sector_code_match():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = ("OFF",)

    assert resolve_sector_code("Office", connection_factory=lambda: conn) == "OFF"
    conn.close.assert_called_once()


def test_resolve_sector_code_fallback_to_raw():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = None

    assert resolve_sector_code("CustomSector", connection_factory=lambda: conn) == "CustomSector"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("1.0", "1"),
        ("1.10", "1.1"),
        ("ABC", "ABC"),
        (2, "2"),
    ],
)
def test_format_code_text(raw, expected):
    assert format_code_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, (None, None)),
        ("1", ("1", None)),
        ("1.0", ("1", None)),  # Decimal normalize drops trailing .0 before split
        ("1.2", ("1.0", "1.2")),
        ("2.30", ("2.0", "2.3")),
    ],
)
def test_split_l1_l2_code(raw, expected):
    assert split_l1_l2_code(raw) == expected


def test_is_effectively_blank_row():
    blank = pd.Series([None, "", float("nan"), "  "])
    filled = pd.Series([None, "x", None])
    assert is_effectively_blank_row(blank) is True
    assert is_effectively_blank_row(filled) is False


def test_infer_l3_row_type():
    assert infer_l3_row_type(1, "m2", 10, 10) == "ITEM"
    assert infer_l3_row_type(None, None, None, None) == "HEADING"
    assert infer_l3_row_type(1, "m2", None, 10) == "HEADING"


def test_decimal_fits_and_coerce():
    assert decimal_fits_precision_scale(Decimal("12.34"), 4, 2) is True
    assert decimal_fits_precision_scale(Decimal("123.45"), 4, 2) is False
    assert coerce_decimal_to_precision_scale(None, 5, 2) is None
    assert coerce_decimal_to_precision_scale(Decimal("1.235"), 5, 2) == Decimal("1.24")
    assert coerce_decimal_to_precision_scale(Decimal("9999.99"), 4, 2) is None


def test_workbook_sheet_lookup_and_resolve():
    names = ["Project Information - 1", "SUMMARY", "LineItem_L3"]
    lookup = workbook_sheet_lookup(names)
    assert lookup["project information - 1"] == "Project Information - 1"
    assert resolve_sheet_name("ProjectInformation", names) == "Project Information - 1"
    assert resolve_sheet_name("ProjectQuants", ["nope"]) is None


def test_source_sheet_name_and_aliases_set():
    df = pd.DataFrame({"a": [1]})
    df.attrs["source_sheet_name"] = "Actual Tab"
    assert source_sheet_name(df, "ProjectInformation") == "Actual Tab"
    assert source_sheet_name(None, "Fallback") == "Fallback"
    assert source_sheet_name(pd.DataFrame(), "Fallback") == "Fallback"
    aliases = all_base_sheet_names_and_aliases()
    assert "projectinformation" in aliases
    assert "project information - 1" in aliases
