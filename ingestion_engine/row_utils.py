"""Shared row helpers for normalization and staging."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.coercion import clean_value, to_decimal


def is_effectively_blank_row(row: pd.Series) -> bool:
    for value in row.values:
        if clean_value(value) is not None:
            return False
    return True


def infer_l3_row_type(quantity, unit, rate, total_cost) -> str:
    has_qty = to_decimal(quantity) is not None
    has_unit = clean_value(unit) is not None
    has_rate = to_decimal(rate) is not None
    has_total = to_decimal(total_cost) is not None
    return "ITEM" if (has_qty and has_unit and has_rate and has_total) else "HEADING"
