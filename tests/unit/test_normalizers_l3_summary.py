"""Unit tests for L3 and SUMMARY normalizers with synthetic grids."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from ingestion_engine.config import IngestionConfig
from ingestion_engine.workbook.normalizers.l3 import (
    L3SheetNormalizer,
    find_contiguous_metric_blocks,
    find_l3_metric_header_row,
)
from ingestion_engine.workbook.normalizers.summary import (
    SummaryNormalizer,
    extract_summary_tenderer_totals,
)


def _test_config() -> IngestionConfig:
    return IngestionConfig(
        process_adjustments=False,
        debug_level2=False,
        sql_server="T",
        sql_db="T",
    )


def test_find_l3_metric_header_and_blocks():
    raw = pd.DataFrame(
        [
            [None, "Alpha", None, None, None, "Beta", None, None, None],
            ["Desc", "Qty", "Unit", "Rate", "Total", "Qty", "Unit", "Rate", "Total"],
            ["Dig", 2, "m3", 10, 20, 3, "m3", 12, 36],
        ]
    )
    assert find_l3_metric_header_row(raw) == 1
    blocks = find_contiguous_metric_blocks(raw.iloc[1].tolist(), ("qty", "unit", "rate", "total"))
    assert blocks == [(1, 2, 3, 4), (5, 6, 7, 8)]


def test_l3_normalizer_selects_first_block_without_contractor():
    # Layout expected by L3SheetNormalizer: col0 unused/ref, col1 description, then metrics.
    raw = pd.DataFrame(
        [
            [None, None, "Alpha", None, None, None],
            [None, "Desc", "Qty", "Unit", "Rate", "Total"],
            ["x", "Dig", 2, "m3", 10, 20],
            ["x", "Note", None, None, None, None],
        ]
    )
    out = L3SheetNormalizer().normalize(raw, l2_code="1.1", l2_name="Substructure")
    dig = out[out["ItemDescription"] == "Dig"].iloc[0]
    assert dig["Quantity"] == 2
    assert dig["TotalCost"] == 20
    assert dig["RowType"] == "ITEM"
    note = out[out["ItemDescription"] == "Note"].iloc[0]
    assert note["RowType"] == "HEADING"


def test_l3_normalizer_requires_header():
    with pytest.raises(ValueError, match="Could not detect L3 metric header"):
        L3SheetNormalizer().normalize(pd.DataFrame([["a", "b"], ["c", "d"]]))


def test_summary_normalizer_builds_l2_rows():
    raw = pd.DataFrame(
        [
            ["Ref", "Element", "Rate", "Total"],
            ["1.0", "Substructure", 10, 100],
            ["1.1", "Excavation", 10, 100],
            ["1.2", "Piling", 20, 200],
        ]
    )
    with patch(
        "ingestion_engine.workbook.normalizers.summary.get_ingestion_config",
        return_value=_test_config(),
    ):
        out = SummaryNormalizer().normalize(raw)
    assert set(out["L2Code"].tolist()) == {"1.1", "1.2"}
    assert out.loc[out["L2Code"] == "1.1", "TotalCost"].iloc[0] == 100
    # "1.0" normalizes to "1" via format_code_text before L1/L2 split
    assert out.loc[out["L2Code"] == "1.1", "L1Code"].iloc[0] == "1"


def test_summary_normalizer_empty_without_header():
    with patch(
        "ingestion_engine.workbook.normalizers.summary.get_ingestion_config",
        return_value=_test_config(),
    ):
        out = SummaryNormalizer().normalize(pd.DataFrame([["a", "b"], [1, 2]]))
    assert out.empty


def test_extract_summary_tenderer_totals():
    # Contractor labels live on the detected header row so forward-fill can name blocks.
    raw = pd.DataFrame(
        [
            ["Ref", "Element", "Alpha", None, "Beta", None],
            [None, None, "Rate", "Total", "Rate", "Total"],
            ["1.1", "Excavate", 1, 10, 2, 20],
            ["Total tender sum (final adjusted)", None, None, 1000, None, 1100],
            ["Variance to budget", None, None, -50, None, -20],
        ]
    )
    totals = extract_summary_tenderer_totals(raw)
    by_label = {t["TendererLabel"]: t for t in totals}
    assert by_label["Alpha"]["FinalAdjustedTenderSum"] == Decimal("1000")
    assert by_label["Alpha"]["VarianceToBudget"] == Decimal("-50")
    assert by_label["Alpha"]["ConstructionBudget"] == Decimal("1050")
    assert by_label["Beta"]["FinalAdjustedTenderSum"] == Decimal("1100")
