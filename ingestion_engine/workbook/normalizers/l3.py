"""Level 3 (LineItem) sheet normalizer."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.coercion import normalize_text
from ingestion_engine.row_utils import infer_l3_row_type
from ingestion_engine.workbook.normalizers.base import SheetNormalizer


def find_l3_metric_header_row(raw_df: pd.DataFrame) -> int | None:
    for idx in range(len(raw_df)):
        row_values = [normalize_text(v) for v in raw_df.iloc[idx].tolist()]
        if not row_values:
            continue
        qty_count = sum(1 for v in row_values if v in {"qty", "quantity"})
        unit_count = sum(1 for v in row_values if v in {"unit", "uom"})
        rate_count = sum(1 for v in row_values if v == "rate")
        total_count = sum(1 for v in row_values if v in {"total", "totalcost", "amount", "value"})
        if qty_count >= 1 and unit_count >= 1 and rate_count >= 1 and total_count >= 1:
            return idx
    return None


def find_contiguous_metric_blocks(
    header_row: list,
    expected_tokens: tuple[str, ...],
) -> list[tuple[int, ...]]:
    tokens = [normalize_text(v) for v in header_row]
    blocks: list[tuple[int, ...]] = []
    exp_len = len(expected_tokens)
    for i in range(0, len(tokens) - exp_len + 1):
        if tuple(tokens[i : i + exp_len]) == expected_tokens:
            blocks.append(tuple(range(i, i + exp_len)))
    return blocks


class L3SheetNormalizer(SheetNormalizer):
    canonical_name = "LineItem_L3"

    def normalize(
        self,
        raw_df: pd.DataFrame,
        *,
        l2_code: str | None = None,
        l2_name: str | None = None,
        selected_contractor: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        header_idx = find_l3_metric_header_row(raw_df)
        if header_idx is None:
            raise ValueError("Could not detect L3 metric header row (Qty/Unit/Rate/Total).")

        header_row = raw_df.iloc[header_idx].tolist()
        data_df = raw_df.iloc[header_idx + 1 :].copy()
        if data_df.empty:
            return pd.DataFrame(
                columns=[
                    "L2Code",
                    "L2Name",
                    "ItemDescription",
                    "Quantity",
                    "Unit",
                    "Rate",
                    "TotalCost",
                ]
            )

        blocks = find_contiguous_metric_blocks(header_row, ("qty", "unit", "rate", "total"))
        selected_block = self.contractor.select_metric_block_for_contractor(
            raw_df,
            header_idx,
            blocks,
            selected_contractor,
        )
        if selected_block is None:
            raise ValueError("Could not resolve first Qty/Unit/Rate/Total block in L3 sheet.")
        qty_col, unit_col, rate_col, total_col = selected_block

        item_col = 1 if data_df.shape[1] > 1 else 0

        out = pd.DataFrame()
        out["L2Code"] = l2_code
        out["L2Name"] = l2_name
        out["ItemDescription"] = data_df.iloc[:, item_col]
        out["Quantity"] = data_df.iloc[:, qty_col]
        out["Unit"] = data_df.iloc[:, unit_col]
        out["Rate"] = data_df.iloc[:, rate_col]
        out["TotalCost"] = data_df.iloc[:, total_col]
        out["RowType"] = out.apply(
            lambda r: infer_l3_row_type(
                r.get("Quantity"), r.get("Unit"), r.get("Rate"), r.get("TotalCost")
            ),
            axis=1,
        )
        out = out.dropna(how="all")
        return out
