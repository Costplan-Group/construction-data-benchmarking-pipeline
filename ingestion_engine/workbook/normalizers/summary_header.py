"""SUMMARY sheet: header row and metric block detection."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.coercion import normalize_text


def detect_summary_header_row(raw_df: pd.DataFrame, max_rows: int = 10) -> int | None:
    for i in range(min(max_rows, len(raw_df))):
        row_tokens = [normalize_text(v) for v in raw_df.iloc[i].tolist()]
        has_code_col = any(t in {"ref", "reference", "code"} for t in row_tokens)
        has_name_col = any(t in {"element", "name", "l2name"} for t in row_tokens)
        if has_code_col and has_name_col:
            return i
    return None


def detect_summary_column_indices(
    header_row: list,
) -> tuple[int | None, int | None, int | None, int | None]:
    ref_col = name_col = rate_col = total_col = None
    for c, value in enumerate(header_row):
        token = normalize_text(value)
        if ref_col is None and token in {"ref", "reference", "code"}:
            ref_col = c
        elif name_col is None and token in {"element", "name", "l2name"}:
            name_col = c
        elif rate_col is None and token == "rate":
            rate_col = c
        elif total_col is None and token in {
            "averagetender",
            "total",
            "totalcost",
            "amount",
            "value",
            "cost",
        }:
            total_col = c
    return ref_col, name_col, rate_col, total_col


def detect_contractor_metric_blocks(
    raw_df: pd.DataFrame,
    header_idx: int,
    scan_rows: int = 14,
) -> tuple[int | None, list[tuple[int, int]]]:
    contractor_metric_row_idx = None
    detected_blocks: list[tuple[int, int]] = []
    max_pairs = -1
    for i in range(header_idx, min(header_idx + scan_rows, len(raw_df))):
        row_tokens = [normalize_text(v) for v in raw_df.iloc[i].tolist()]
        row_blocks: list[tuple[int, int]] = []
        for c in range(0, len(row_tokens) - 1):
            if row_tokens[c] == "rate" and row_tokens[c + 1] in {
                "total",
                "totalcost",
                "amount",
                "value",
            }:
                row_blocks.append((c, c + 1))
        if len(row_blocks) > max_pairs:
            max_pairs = len(row_blocks)
            contractor_metric_row_idx = i
            detected_blocks = row_blocks
    return contractor_metric_row_idx, detected_blocks
