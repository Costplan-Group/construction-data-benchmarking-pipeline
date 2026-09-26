"""ProjectQuants sheet normalizer."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from ingestion_engine.coercion import normalize_text, to_decimal
from ingestion_engine.workbook.normalizers.base import SheetNormalizer


class ProjectQuantsNormalizer(SheetNormalizer):
    canonical_name = "ProjectQuants"

    def normalize(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        out = df.copy()
        rename_map = {}
        for col in out.columns:
            n = normalize_text(col)
            if n in {"projectquantcode", "code", "ref", "reference"}:
                rename_map[col] = "ProjectQuantCode"
            elif n in {"projectquantname", "name", "names", "projectquant", "description"}:
                rename_map[col] = "ProjectQuantName"
            elif n in {"qty", "quantity", "quant"}:
                rename_map[col] = "Qty"
            elif n in {"unit", "uom"}:
                rename_map[col] = "Unit"
            elif n in {"comment", "comments", "note", "notes"}:
                rename_map[col] = "Comment"
        out = out.rename(columns=rename_map)

        if "ProjectQuantCode" not in out.columns and "ProjectQuantName" in out.columns:
            out["ProjectQuantCode"] = [f"PQ-{i + 1:03d}" for i in range(len(out))]
        return out


def extract_gifa_from_project_quants(df: pd.DataFrame) -> Decimal | None:
    if df is None or df.empty:
        return None

    name_col = None
    for candidate in ("ProjectQuantName", "Name"):
        if candidate in df.columns:
            name_col = candidate
            break
    if name_col is None or "Qty" not in df.columns:
        return None

    for _, row in df.iterrows():
        label = normalize_text(row.get(name_col))
        if not label:
            continue
        if label in {"gifa", "grossinternalfloorarea", "grossinternalarea"} or "gifa" in label:
            qty = to_decimal(row.get("Qty"))
            if qty is not None:
                return qty
    return None
