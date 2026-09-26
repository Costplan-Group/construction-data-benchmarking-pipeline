"""ElementQuants_L2 sheet normalizer."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.coercion import clean_value, normalize_text
from ingestion_engine.workbook.code_utils import format_code_text
from ingestion_engine.workbook.normalizers.base import SheetNormalizer


class ElementQuantsNormalizer(SheetNormalizer):
    canonical_name = "ElementQuants_L2"

    @staticmethod
    def _rename_element_quant_columns(frame: pd.DataFrame) -> pd.DataFrame:
        rename_map = {}
        for col in frame.columns:
            n = normalize_text(col)
            if n in {"l2code", "code", "ref", "reference"}:
                rename_map[col] = "L2Code"
            elif n in {"elementalquants", "element", "name", "l2name"}:
                rename_map[col] = "L2Name"
            elif n in {"quant", "quantity", "qty"}:
                rename_map[col] = "Qty"
            elif n in {"unit", "uom"}:
                rename_map[col] = "Unit"
            elif n in {"comment", "comments", "note", "notes"}:
                rename_map[col] = "Comment"
            elif n in {"quanttype", "quanttypecode"}:
                rename_map[col] = "QuantTypeCode"
        return frame.rename(columns=rename_map)

    def normalize(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        out = self._rename_element_quant_columns(df.copy())

        if "L2Code" not in out.columns:
            probe = df.copy()
            probe.columns = [str(c).strip() for c in probe.columns]
            header_idx = None
            for i in range(min(15, len(probe))):
                tokens = {normalize_text(v) for v in probe.iloc[i].tolist()}
                has_code = "code" in tokens or "l2code" in tokens or "ref" in tokens
                has_element = "element" in tokens or "l2name" in tokens or "name" in tokens
                has_qty = "qty" in tokens or "quantity" in tokens or "quant" in tokens
                if has_code and (has_element or has_qty):
                    header_idx = i
                    break
            if header_idx is not None:
                header_vals = [
                    str(clean_value(v)).strip() if clean_value(v) is not None else f"col_{idx}"
                    for idx, v in enumerate(probe.iloc[header_idx].tolist())
                ]
                body = probe.iloc[header_idx + 1 :].copy()
                body.columns = header_vals
                body = body.reset_index(drop=True)
                out = self._rename_element_quant_columns(body)

        if "L2Code" in out.columns:
            out["L2Code"] = out["L2Code"].map(format_code_text)
        elif "L2Name" in out.columns:
            out["L2Code"] = [f"L2-{i + 1:03d}" for i in range(len(out))]
        if "QuantTypeCode" not in out.columns:
            out["QuantTypeCode"] = "DEFAULT"
        return out
