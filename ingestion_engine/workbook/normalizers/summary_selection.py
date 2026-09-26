"""SUMMARY sheet: contractor block selection."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.contractor import ContractorSelector


def select_summary_contractor_block(
    contractor: ContractorSelector,
    raw_df: pd.DataFrame,
    header_row: list,
    contractor_metric_row_idx: int,
    blocks: list[tuple[int, int]],
    selected_contractor: str | None,
) -> tuple[int, int] | None:
    selected_block = contractor.select_summary_block_from_header_row(
        header_row,
        blocks,
        selected_contractor,
    )
    if selected_block is None:
        selected_block = contractor.select_metric_block_for_contractor(
            raw_df,
            contractor_metric_row_idx,
            blocks,
            selected_contractor,
        )
    return selected_block
