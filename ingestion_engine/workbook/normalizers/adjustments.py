"""Adjustments sheet normalizer."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.coercion import normalize_text
from ingestion_engine.workbook.normalizers.base import SheetNormalizer


class AdjustmentsNormalizer(SheetNormalizer):
    canonical_name = "Adjustments"

    def normalize(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        rename_map = {}
        for col in out.columns:
            n = normalize_text(col)
            if n in {"adjcategory", "category"}:
                rename_map[col] = "AdjCategory"
            elif n in {"adjsubtype", "subtype"}:
                rename_map[col] = "AdjSubType"
            elif n in {"amount", "value", "total"}:
                rename_map[col] = "Amount"
            elif n == "method":
                rename_map[col] = "Method"
            elif n in {"ratepercent", "percent", "rate"}:
                rename_map[col] = "RatePercent"
            elif n == "appliedtobase":
                rename_map[col] = "AppliedToBase"
            elif n == "includedincomparison":
                rename_map[col] = "IncludedInComparison"
        return out.rename(columns=rename_map)
