"""Contractor detection and metric column selection for multi-contractor workbooks."""

from __future__ import annotations

import pandas as pd

from ingestion_engine.coercion import clean_value, normalize_text


class ContractorSelector:
    """Resolve selected contractor and metric columns/blocks in workbook sheets."""

    def get_selected_contractor(self, project_info_df: pd.DataFrame) -> str | None:
        if project_info_df is None or project_info_df.empty:
            return None

        preferred_cols = ["SelectedContractor"]
        for col in preferred_cols:
            if col in project_info_df.columns:
                series = project_info_df[col].dropna()
                if not series.empty:
                    contractor = clean_value(series.iloc[0])
                    return str(contractor).strip() if contractor else None
        return None

    def detect_from_sheet_row(self, raw_df: pd.DataFrame) -> str | None:
        if raw_df is None or raw_df.empty:
            return None

        first_row_values = None
        for _, row in raw_df.iterrows():
            vals = [clean_value(v) for v in row.tolist()]
            if any(v is not None for v in vals):
                first_row_values = vals
                break

        if not first_row_values:
            return None

        text_values = [str(v).strip() for v in first_row_values if v is not None]
        if not text_values:
            return None

        for text in text_values:
            low = text.lower()
            if "selected contractor" in low and ":" in text:
                candidate = text.split(":", 1)[1].strip()
                if candidate:
                    return candidate

        for i, text in enumerate(text_values):
            low = text.lower()
            if "selected contractor" in low or low == "contractor" or "contractor name" in low:
                for j in range(i + 1, len(text_values)):
                    candidate = text_values[j].strip()
                    if candidate:
                        return candidate

        return None

    def detect_from_workbook(self, xls: pd.ExcelFile) -> str | None:
        for sheet in xls.sheet_names:
            try:
                raw_df = pd.read_excel(
                    xls,
                    sheet_name=sheet,
                    engine="openpyxl",
                    header=None,
                    nrows=5,
                )
            except Exception:
                continue

            contractor = self.detect_from_sheet_row(raw_df)
            if contractor:
                return contractor

        return None

    def resolve_metric_column(
        self,
        df: pd.DataFrame,
        metric_aliases: list[str],
        selected_contractor: str | None,
    ) -> str | None:
        columns = [str(c) for c in df.columns]
        norm_to_original = {normalize_text(c): c for c in columns}

        for alias in metric_aliases:
            n = normalize_text(alias)
            if n in norm_to_original:
                return norm_to_original[n]

        contractor_key = normalize_text(selected_contractor) if selected_contractor else ""

        if contractor_key:
            for col in columns:
                n = normalize_text(col)
                if contractor_key in n and any(normalize_text(a) in n for a in metric_aliases):
                    return col

        metric_candidates = []
        for col in columns:
            n = normalize_text(col)
            if any(normalize_text(a) in n for a in metric_aliases):
                metric_candidates.append(col)
        if len(metric_candidates) == 1:
            return metric_candidates[0]

        return None

    def normalize_contractor_metrics(
        self,
        df: pd.DataFrame,
        selected_contractor: str | None,
        context_name: str,
    ) -> pd.DataFrame:
        metric_specs = {
            "Qty": ["Qty", "Quantity"],
            "Unit": ["Unit", "UOM"],
            "Rate": ["Rate"],
            "TotalCost": ["TotalCost", "Total", "Amount", "Value"],
        }

        resolved = {}
        for canonical, aliases in metric_specs.items():
            col = self.resolve_metric_column(df, aliases, selected_contractor)
            if col is None:
                raise ValueError(
                    f"Could not resolve '{canonical}' column for selected contractor "
                    f"'{selected_contractor or '<unknown>'}' in sheet '{context_name}'."
                )
            resolved[canonical] = col

        out = df.copy()
        for canonical, source_col in resolved.items():
            out[canonical] = out[source_col]

        return out

    @staticmethod
    def forward_fill_header_labels(values: list) -> list[str | None]:
        labels: list[str | None] = []
        current: str | None = None
        for value in values:
            cv = clean_value(value)
            if cv is not None:
                current = str(cv).strip()
            labels.append(current)
        return labels

    def select_metric_block_for_contractor(
        self,
        raw_df: pd.DataFrame,
        metric_row_idx: int,
        blocks: list[tuple[int, ...]],
        selected_contractor: str | None,
    ) -> tuple[int, ...] | None:
        if not blocks:
            return None
        if not selected_contractor:
            return blocks[0]

        contractor_key = normalize_text(selected_contractor)
        if not contractor_key:
            return blocks[0]

        for block in blocks:
            start_col = block[0]
            for r in range(max(0, metric_row_idx - 5), metric_row_idx):
                row_vals = raw_df.iloc[r].tolist()
                left = max(0, start_col - 3)
                right = min(len(row_vals), start_col + 5)
                probe = " ".join(str(v) for v in row_vals[left:right] if clean_value(v) is not None)
                if contractor_key and contractor_key in normalize_text(probe):
                    return block

        contractor_positions: list[int] = []
        for r in range(max(0, metric_row_idx - 8), metric_row_idx):
            row_vals = raw_df.iloc[r].tolist()
            for c, value in enumerate(row_vals):
                cv = clean_value(value)
                if cv is None:
                    continue
                if contractor_key in normalize_text(cv):
                    contractor_positions.append(c)
        if contractor_positions:
            target_col = int(sum(contractor_positions) / len(contractor_positions))
            return min(blocks, key=lambda b: abs(((b[0] + b[-1]) / 2) - target_col))

        if len(blocks) > 1:
            return None

        return blocks[0]

    def select_summary_block_from_header_row(
        self,
        header_row: list,
        blocks: list[tuple[int, int]],
        selected_contractor: str | None,
    ) -> tuple[int, int] | None:
        if not blocks:
            return None
        if not selected_contractor:
            return blocks[0]

        contractor_key = normalize_text(selected_contractor)
        if not contractor_key:
            return blocks[0]

        ff_labels = self.forward_fill_header_labels(header_row)

        for block in blocks:
            start_col, end_col = block[0], block[-1]
            primary_labels = []
            if start_col < len(ff_labels):
                primary_labels.append(ff_labels[start_col])
            if end_col < len(ff_labels):
                primary_labels.append(ff_labels[end_col])
            if any(label and contractor_key in normalize_text(label) for label in primary_labels):
                return block

        for block in blocks:
            start_col, end_col = block[0], block[-1]
            left = max(0, start_col - 1)
            right = min(len(ff_labels), end_col + 2)
            window_labels = [ff_labels[c] for c in range(left, right)]
            if any(label and contractor_key in normalize_text(label) for label in window_labels):
                return block

        contractor_positions: list[int] = []
        for c, value in enumerate(header_row):
            cv = clean_value(value)
            if cv is None:
                continue
            if contractor_key in normalize_text(cv):
                contractor_positions.append(c)
        if contractor_positions:
            target_col = int(sum(contractor_positions) / len(contractor_positions))
            return min(blocks, key=lambda b: abs(((b[0] + b[-1]) / 2) - target_col))

        if len(blocks) > 1:
            return None
        return blocks[0]


# Module-level helpers for backward compatibility
_default_selector = ContractorSelector()

get_selected_contractor = _default_selector.get_selected_contractor
detect_selected_contractor_from_sheet_row = _default_selector.detect_from_sheet_row
detect_selected_contractor_from_workbook = _default_selector.detect_from_workbook
resolve_metric_column = _default_selector.resolve_metric_column
normalize_contractor_metrics = _default_selector.normalize_contractor_metrics
