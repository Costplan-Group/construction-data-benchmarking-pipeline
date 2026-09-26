"""SUMMARY sheet normalizer (Level2 source)."""

from __future__ import annotations

import re

import pandas as pd

from ingestion_engine.coercion import clean_value, normalize_text, to_decimal
from ingestion_engine.config import get_ingestion_config
from ingestion_engine.contractor import ContractorSelector
from ingestion_engine.workbook.code_utils import split_l1_l2_code
from ingestion_engine.workbook.normalizers.base import SheetNormalizer
from ingestion_engine.workbook.normalizers.summary_header import (
    detect_contractor_metric_blocks,
    detect_summary_column_indices,
    detect_summary_header_row,
)
from ingestion_engine.workbook.normalizers.summary_selection import select_summary_contractor_block


def _excel_col_letter_from_zero_based(col_idx: int | None) -> str | None:
    if col_idx is None or col_idx < 0:
        return None
    n = col_idx + 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _attach_summary_debug_metadata(
    out: pd.DataFrame,
    header_idx: int | None,
    metric_row_idx: int | None,
    rate_col: int | None,
    total_col: int | None,
    selected_block: tuple[int, int] | None,
    selected_contractor: str | None,
) -> pd.DataFrame:
    out["__SummaryHeaderRow"] = header_idx
    out["__SummaryMetricRow"] = metric_row_idx
    out["__SummarySelectedRateCol"] = rate_col
    out["__SummarySelectedTotalCol"] = total_col
    out["__SummarySelectedBlock"] = str(selected_block) if selected_block is not None else None
    out["__SummarySelectedContractor"] = selected_contractor

    rate_col_letter = _excel_col_letter_from_zero_based(rate_col)
    total_col_letter = _excel_col_letter_from_zero_based(total_col)
    out["__SummarySelectedRateColLetter"] = rate_col_letter
    out["__SummarySelectedTotalColLetter"] = total_col_letter

    out["__SummaryRateCell"] = out.apply(
        lambda r: (
            f"{rate_col_letter}{int(r['__SummarySourceExcelRow'])}"
            if rate_col_letter is not None and pd.notna(r.get("__SummarySourceExcelRow"))
            else None
        ),
        axis=1,
    )
    out["__SummaryTotalCell"] = out.apply(
        lambda r: (
            f"{total_col_letter}{int(r['__SummarySourceExcelRow'])}"
            if total_col_letter is not None and pd.notna(r.get("__SummarySourceExcelRow"))
            else None
        ),
        axis=1,
    )
    return out


class SummaryNormalizer(SheetNormalizer):
    canonical_name = "Level2"

    def normalize(
        self, raw_df: pd.DataFrame, *, selected_contractor: str | None = None, **kwargs
    ) -> pd.DataFrame:
        header_idx = detect_summary_header_row(raw_df)
        if header_idx is None:
            return pd.DataFrame()

        header_row = raw_df.iloc[header_idx].tolist()
        data_df = raw_df.iloc[header_idx + 1 :].copy()
        if data_df.empty:
            return pd.DataFrame()

        ref_col, name_col, rate_col, total_col = detect_summary_column_indices(header_row)
        selected_block = None
        contractor_metric_row_idx, detected_blocks = detect_contractor_metric_blocks(
            raw_df, header_idx
        )

        if contractor_metric_row_idx is not None:
            blocks = detected_blocks
            selected_block = select_summary_contractor_block(
                self.contractor,
                raw_df,
                header_row,
                contractor_metric_row_idx,
                blocks,
                selected_contractor,
            )
            data_df = raw_df.iloc[contractor_metric_row_idx + 1 :].copy()

            if selected_block is not None:
                rate_col, total_col = selected_block
            elif len(blocks) > 1 and selected_contractor:
                rate_col = None
                total_col = None

        out = pd.DataFrame()
        ref_series = data_df.iloc[:, ref_col] if ref_col is not None else data_df.iloc[:, 0]
        name_series = data_df.iloc[:, name_col] if name_col is not None else data_df.iloc[:, 1]

        l1_codes = []
        l1_names = []
        l2_codes = []
        l2_names = []
        current_l1_code = None
        current_l1_name = None
        for ref_val, name_val in zip(ref_series.tolist(), name_series.tolist(), strict=False):
            l1_code, l2_code = split_l1_l2_code(ref_val)
            name_clean = clean_value(name_val)
            if l2_code is None:
                current_l1_code = l1_code
                current_l1_name = name_clean
                l1_codes.append(l1_code)
                l1_names.append(name_clean)
                l2_codes.append(None)
                l2_names.append(None)
            else:
                l1_codes.append(current_l1_code or l1_code)
                l1_names.append(current_l1_name)
                l2_codes.append(l2_code)
                l2_names.append(name_clean)

        out["L1Code"] = l1_codes
        out["L1Name"] = l1_names
        out["L2Code"] = l2_codes
        out["L2Name"] = l2_names
        out["__SummarySourceRowIdx"] = data_df.index
        out["__SummarySourceExcelRow"] = data_df.index + 1

        if rate_col is not None and total_col is not None:
            rate_values = []
            total_values = []
            for src_idx in out["__SummarySourceRowIdx"].tolist():
                if 0 <= int(src_idx) < len(raw_df):
                    rate_values.append(raw_df.iat[int(src_idx), rate_col])
                    total_values.append(raw_df.iat[int(src_idx), total_col])
                else:
                    rate_values.append(None)
                    total_values.append(None)
            out["Rate"] = rate_values
            out["TotalCost"] = total_values
        else:
            out["Rate"] = None
            out["TotalCost"] = None

        l1_mask = out["L2Code"].isna()
        out.loc[l1_mask, "Rate"] = None
        out.loc[l1_mask, "TotalCost"] = None

        out = _attach_summary_debug_metadata(
            out=out,
            header_idx=header_idx,
            metric_row_idx=contractor_metric_row_idx,
            rate_col=rate_col,
            total_col=total_col,
            selected_block=selected_block,
            selected_contractor=selected_contractor,
        )

        out = out[out["L2Code"].notna()].copy()
        if get_ingestion_config().debug_level2:
            print(
                "[DEBUG_LEVEL2] selected_contractor=",
                selected_contractor or "<unknown>",
                " header_row=",
                header_idx,
                " metric_row=",
                contractor_metric_row_idx,
                " block=",
                selected_block,
                " rate_col=",
                rate_col,
                " total_col=",
                total_col,
            )
            preview_cols = [
                c
                for c in [
                    "L1Code",
                    "L1Name",
                    "L2Code",
                    "L2Name",
                    "Rate",
                    "TotalCost",
                    "__SummaryMetricRow",
                    "__SummarySelectedRateCol",
                    "__SummarySelectedTotalCol",
                    "__SummarySelectedBlock",
                    "__SummarySelectedContractor",
                    "__SummarySourceExcelRow",
                    "__SummaryRateCell",
                    "__SummaryTotalCell",
                ]
                if c in out.columns
            ]
            print("[DEBUG_LEVEL2] preview:")
            try:
                print(out[preview_cols].head(8).to_string(index=False))
            except Exception:
                print(out.head(8).to_string(index=False))
        return out.dropna(how="all")


def extract_summary_tenderer_totals(raw_df: pd.DataFrame) -> list[dict[str, object]]:
    if raw_df is None or raw_df.empty:
        return []

    header_idx = detect_summary_header_row(raw_df)
    if header_idx is None:
        return []

    header_row = raw_df.iloc[header_idx].tolist()
    ff_labels = ContractorSelector.forward_fill_header_labels(header_row)

    metric_row_idx, blocks = detect_contractor_metric_blocks(raw_df, header_idx)
    if metric_row_idx is None or not blocks:
        return []

    final_adjusted_row = None
    variance_row = None
    for i in range(metric_row_idx + 1, len(raw_df)):
        row_vals = [clean_value(v) for v in raw_df.iloc[i].tolist()]
        token = normalize_text(" ".join(str(v) for v in row_vals if v is not None))
        if final_adjusted_row is None and "totaltendersumfinaladjusted" in token:
            final_adjusted_row = i
        if variance_row is None and (
            "variancetobudget" in token
            or "variancefrombudget" in token
            or "variancefromcostplan" in token
        ):
            variance_row = i
    if final_adjusted_row is None and variance_row is None:
        return []

    results: list[dict[str, object]] = []
    for rate_col, total_col in blocks:
        label_raw = ""
        if total_col < len(ff_labels) and ff_labels[total_col]:
            label_raw = str(ff_labels[total_col] or "")
        elif rate_col < len(ff_labels) and ff_labels[rate_col]:
            label_raw = str(ff_labels[rate_col] or "")
        label = re.sub(r"\s+", " ", label_raw).strip()
        label_token = normalize_text(label)
        if not label or "averagetender" in label_token:
            continue

        final_adjusted = None
        variance_to_budget = None
        construction_budget = None

        if final_adjusted_row is not None and total_col < raw_df.shape[1]:
            final_adjusted = to_decimal(raw_df.iat[final_adjusted_row, total_col])
        if variance_row is not None and total_col < raw_df.shape[1]:
            variance_to_budget = to_decimal(raw_df.iat[variance_row, total_col])
        if final_adjusted is not None and variance_to_budget is not None:
            construction_budget = final_adjusted - variance_to_budget

        results.append(
            {
                "TendererLabel": label,
                "FinalAdjustedTenderSum": final_adjusted,
                "VarianceToBudget": variance_to_budget,
                "ConstructionBudget": construction_budget,
            }
        )
    return results
