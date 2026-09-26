"""Additional contractor selector unit tests."""

from __future__ import annotations

import pandas as pd
import pytest

from ingestion_engine.contractor import ContractorSelector
from ingestion_engine.workbook.normalizers.summary_selection import select_summary_contractor_block


def test_normalize_contractor_metrics_and_resolve():
    selector = ContractorSelector()
    df = pd.DataFrame(
        [
            {
                "Qty": 1,
                "Unit": "m2",
                "Rate": 2,
                "TotalCost": 2,
            }
        ]
    )
    out = selector.normalize_contractor_metrics(df, None, "test")
    assert list(out["TotalCost"]) == [2]

    with pytest.raises(ValueError, match="Could not resolve"):
        selector.normalize_contractor_metrics(pd.DataFrame([{"A": 1}]), "X", "bad")


def test_select_metric_block_by_contractor_name():
    selector = ContractorSelector()
    # Wide grid so each contractor label sits only near its own block window.
    raw = pd.DataFrame(
        [
            [
                None,
                "AlphaOnly",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "BetaOnly",
                None,
                None,
                None,
            ],
            [
                None,
                "Qty",
                "Unit",
                "Rate",
                "Total",
                None,
                None,
                None,
                None,
                "Qty",
                "Unit",
                "Rate",
                "Total",
            ],
        ]
    )
    blocks = [(1, 2, 3, 4), (9, 10, 11, 12)]
    assert selector.select_metric_block_for_contractor(raw, 1, blocks, "BetaOnly") == (
        9,
        10,
        11,
        12,
    )
    assert selector.select_metric_block_for_contractor(raw, 1, blocks, "AlphaOnly") == (
        1,
        2,
        3,
        4,
    )
    assert selector.select_metric_block_for_contractor(raw, 1, [], "BetaOnly") is None
    assert selector.select_metric_block_for_contractor(raw, 1, blocks, None) == blocks[0]


def test_select_summary_block_from_header_and_wrapper():
    selector = ContractorSelector()
    header = ["Ref", "Element", "Alpha", None, "Beta", None]
    blocks = [(2, 3), (4, 5)]
    assert selector.select_summary_block_from_header_row(header, blocks, "Beta") == (4, 5)

    raw = pd.DataFrame([header, ["x"] * 6])
    wrapped = select_summary_contractor_block(selector, raw, header, 0, blocks, "Alpha")
    assert wrapped == (2, 3)


def test_detect_from_sheet_row_label_then_value():
    selector = ContractorSelector()
    df = pd.DataFrame([["Selected contractor", "Gamma Ltd", None]])
    assert selector.detect_from_sheet_row(df) == "Gamma Ltd"
