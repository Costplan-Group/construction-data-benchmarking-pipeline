"""Concrete SheetStager implementations."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from ingestion_engine.coercion import clean_value, to_bit, to_decimal, to_int
from ingestion_engine.contractor import get_selected_contractor
from ingestion_engine.project_attributes import CHOICE_FIELDS, canonical_choice, is_blank
from ingestion_engine.row_utils import infer_l3_row_type
from ingestion_engine.schema import COLUMN_MAPS, STAGING_TABLES
from ingestion_engine.staging.base import SheetStager
from ingestion_engine.staging.decimal_coerce import coerce_decimal_to_precision_scale
from ingestion_engine.workbook.aliases import source_sheet_name
from ingestion_engine.workbook.normalizers.project_information import (
    extract_tenderers_from_project_information_df,
)


def _staged_choice(field: str, value, allowed: tuple[str, ...]) -> str | None:
    if is_blank(value):
        return None
    canonical = canonical_choice(value, allowed)
    if canonical is None:
        raise ValueError(
            f"Unvalidated {field} value {value!r} reached staging; allowed: {', '.join(allowed)}"
        )
    return canonical


class ProjectInformationStager(SheetStager):
    table_key = "ProjectInformation"

    def build_rows(
        self,
        load_batch_id: str,
        source_file: str,
        df: pd.DataFrame,
        *,
        fallback_gifa: Decimal | None = None,
        **kwargs,
    ) -> list[dict]:
        rows = []
        for idx, row in self.iter_data_rows(df):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": int(idx) + 2,
                "SourceFileName": source_file,
            }
            for excel_col, db_col in COLUMN_MAPS["ProjectInformation"].items():
                mapped[db_col] = clean_value(row.get(excel_col))

            region_value = clean_value(row.get("Region"))
            if region_value is not None:
                mapped["LocationLabel"] = region_value

            if self.resolve_sector_code:
                mapped["SectorCode"] = self.resolve_sector_code(mapped.get("SectorCode"))

            mapped["Demolition"] = to_bit(row.get("Demolition"))
            mapped["NewBuild"] = to_bit(row.get("NewBuild"))
            mapped["Refurbishment"] = to_bit(row.get("Refurbishment"))
            mapped["HorizontalExtension"] = to_bit(row.get("HorizontalExtension"))
            mapped["VerticalExtension"] = to_bit(row.get("VerticalExtension"))
            mapped["Basement"] = to_bit(row.get("Basement"))
            mapped["Asbestos"] = to_bit(row.get("Asbestos"))
            mapped["Contamination"] = to_bit(row.get("Contamination"))
            for field, allowed in CHOICE_FIELDS.items():
                mapped[field] = _staged_choice(field, row.get(field), allowed)
            mapped["ComplexityRating"] = to_int(row.get("ComplexityRating"))
            mapped["Occupied"] = to_bit(row.get("Occupied"))
            mapped["NrOfStoreys"] = to_int(row.get("NrOfStoreys"))
            mapped["TotalHeightGroundToRoof"] = to_decimal(row.get("TotalHeightGroundToRoof"))
            mapped["BasementArea"] = to_decimal(row.get("BasementArea"))
            mapped["BasementHeight"] = to_decimal(row.get("BasementHeight"))
            mapped["ProgrammeLengthInWeeks"] = to_int(row.get("ProgrammeLengthInWeeks"))
            mapped["GIFA"] = to_decimal(row.get("GIFA"))
            if mapped["GIFA"] is None and fallback_gifa is not None:
                mapped["GIFA"] = fallback_gifa
            rows.append(mapped)
        return rows


class ProjectTendererStager(SheetStager):
    table_key = "ProjectTenderer"

    def build_rows(
        self,
        load_batch_id: str,
        source_file: str,
        df: pd.DataFrame,
        **kwargs,
    ) -> list[dict]:
        rows = []
        selected_contractor = (get_selected_contractor(df) or "").strip()
        selected_norm = selected_contractor.casefold()
        tenderers = extract_tenderers_from_project_information_df(df)
        summary_totals = df.attrs.get("summary_tenderer_totals")
        summary_totals_by_label: dict[str, dict[str, Decimal | None]] = {}
        if isinstance(summary_totals, pd.DataFrame) and not summary_totals.empty:
            for _, row in summary_totals.iterrows():
                label = str(clean_value(row.get("TendererLabel")) or "").strip()
                if not label:
                    continue
                summary_totals_by_label[label.casefold()] = {
                    "FinalAdjustedTenderSum": to_decimal(row.get("FinalAdjustedTenderSum")),
                    "VarianceToBudget": to_decimal(
                        row.get("VarianceToBudget", row.get("VarianceToCostplan"))
                    ),
                    "ConstructionBudget": to_decimal(row.get("ConstructionBudget")),
                }

        table_columns: set[str] = set()
        if self.fetch_all:
            table_columns = {
                str(r.get("COLUMN_NAME"))
                for r in self.fetch_all(
                    """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'stg'
              AND TABLE_NAME = 'ProjectTenderer'
            """
                )
            }
        decimal_meta = self._get_decimal_meta(STAGING_TABLES["ProjectTenderer"])
        tenderer_decimal_cols = (
            "FinalAdjustedTenderSum",
            "VarianceToBudget",
            "VarianceToCostplan",
            "ConstructionBudget",
        )

        for idx, (label, name) in enumerate(tenderers, start=1):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": idx,
                "SourceFileName": source_file,
                "TendererLabel": label,
                "TendererName": name,
                "IsSelected": 1 if selected_norm and name.casefold() == selected_norm else 0,
            }
            totals = summary_totals_by_label.get(name.casefold()) or summary_totals_by_label.get(
                label.casefold()
            )
            if totals:
                if "FinalAdjustedTenderSum" in table_columns:
                    mapped["FinalAdjustedTenderSum"] = totals.get("FinalAdjustedTenderSum")
                if "VarianceToBudget" in table_columns:
                    mapped["VarianceToBudget"] = totals.get("VarianceToBudget")
                elif "VarianceToCostplan" in table_columns:
                    mapped["VarianceToCostplan"] = totals.get("VarianceToBudget")
                if "ConstructionBudget" in table_columns:
                    mapped["ConstructionBudget"] = totals.get("ConstructionBudget")

            mapped = self.coerce_row_decimals(mapped, tenderer_decimal_cols, decimal_meta)
            rows.append(mapped)
        return rows


class ProjectQuantsStager(SheetStager):
    table_key = "ProjectQuants"

    def build_rows(
        self, load_batch_id: str, source_file: str, df: pd.DataFrame, **kwargs
    ) -> list[dict]:
        rows = []
        for idx, row in self.iter_data_rows(df):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": int(idx) + 2,
                "SourceFileName": source_file,
            }
            for excel_col, db_col in COLUMN_MAPS["ProjectQuants"].items():
                mapped[db_col] = clean_value(row.get(excel_col))
            mapped["Qty"] = to_decimal(row.get("Qty"))
            rows.append(mapped)
        return rows


class ElementQuantsL2Stager(SheetStager):
    table_key = "ElementQuants_L2"

    def build_rows(
        self, load_batch_id: str, source_file: str, df: pd.DataFrame, **kwargs
    ) -> list[dict]:
        rows = []
        for idx, row in self.iter_data_rows(df):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": int(idx) + 2,
                "SourceFileName": source_file,
            }
            for excel_col, db_col in COLUMN_MAPS["ElementQuants_L2"].items():
                mapped[db_col] = clean_value(row.get(excel_col))
            mapped["Qty"] = to_decimal(row.get("Qty"))
            rows.append(mapped)
        return rows


class Level2Stager(SheetStager):
    table_key = "Level2"

    def build_rows(
        self, load_batch_id: str, source_file: str, df: pd.DataFrame, **kwargs
    ) -> list[dict]:
        rows = []
        decimal_meta = self._get_decimal_meta(STAGING_TABLES["Level2"])
        level2_decimal_cols = ("Rate", "TotalCost")
        precision_errors = 0
        display_sheet = source_sheet_name(df, "SUMMARY")

        for idx, row in self.iter_data_rows(df):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": int(idx) + 2,
                "SourceFileName": source_file,
            }
            for excel_col, db_col in COLUMN_MAPS["Level2"].items():
                mapped[db_col] = clean_value(row.get(excel_col))

            mapped["Rate"] = to_decimal(row.get("Rate"))
            mapped["TotalCost"] = to_decimal(row.get("TotalCost"))

            if mapped["TotalCost"] is None:
                if self.log_validation_error:
                    self.log_validation_error(
                        load_batch_id=load_batch_id,
                        sheet_name=display_sheet,
                        row_num=int(idx) + 2,
                        column_name="TotalCost",
                        error_type="MISSING_TOTALCOST_SKIPPED",
                        error_message=(
                            f"Skipped {display_sheet} row because TotalCost is null/blank for selected contractor."
                        ),
                        severity="WARNING",
                        row_data={
                            "L1Code": clean_value(row.get("L1Code")),
                            "L1Name": clean_value(row.get("L1Name")),
                            "L2Code": clean_value(row.get("L2Code")),
                            "L2Name": clean_value(row.get("L2Name")),
                            "Rate": clean_value(row.get("Rate")),
                            "TotalCost": clean_value(row.get("TotalCost")),
                            "SummaryHeaderRow": clean_value(row.get("__SummaryHeaderRow")),
                            "SummaryMetricRow": clean_value(row.get("__SummaryMetricRow")),
                            "SummarySelectedRateCol": clean_value(
                                row.get("__SummarySelectedRateCol")
                            ),
                            "SummarySelectedTotalCol": clean_value(
                                row.get("__SummarySelectedTotalCol")
                            ),
                            "SummarySelectedBlock": clean_value(row.get("__SummarySelectedBlock")),
                            "SummarySelectedContractor": clean_value(
                                row.get("__SummarySelectedContractor")
                            ),
                            "SummarySourceExcelRow": clean_value(
                                row.get("__SummarySourceExcelRow")
                            ),
                            "SummaryRateCell": clean_value(row.get("__SummaryRateCell")),
                            "SummaryTotalCell": clean_value(row.get("__SummaryTotalCell")),
                        },
                    )
                continue

            for dec_col in level2_decimal_cols:
                dec_val = mapped.get(dec_col)
                if dec_val is None or not isinstance(dec_val, Decimal):
                    continue
                if dec_col not in decimal_meta:
                    continue
                precision, scale = decimal_meta[dec_col]
                coerced = coerce_decimal_to_precision_scale(dec_val, precision, scale)
                if coerced is None:
                    precision_errors += 1
                    if self.log_validation_error:
                        self.log_validation_error(
                            load_batch_id=load_batch_id,
                            sheet_name=display_sheet,
                            row_num=int(idx) + 2,
                            column_name=dec_col,
                            error_type="DECIMAL_PRECISION",
                            error_message=(
                                f"Value '{dec_val}' does not fit DECIMAL({precision},{scale}) "
                                f"for column '{dec_col}' in {STAGING_TABLES['Level2']}."
                            ),
                        )
                else:
                    mapped[dec_col] = coerced

            rows.append(mapped)

        if precision_errors > 0:
            raise ValueError(
                f"{display_sheet} contains {precision_errors} value(s) that exceed SQL decimal precision/scale. "
                "See stg.ValidationError for row+column details."
            )
        return rows


class LineItemL3Stager(SheetStager):
    table_key = "LineItem_L3"

    def build_rows(
        self, load_batch_id: str, source_file: str, df: pd.DataFrame, **kwargs
    ) -> list[dict]:
        rows = []
        display_order_by_l2: dict[str, int] = {}

        for idx, row in self.iter_data_rows(df):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": int(idx) + 2,
                "SourceFileName": source_file,
            }
            for excel_col, db_col in COLUMN_MAPS["LineItem_L3"].items():
                mapped[db_col] = clean_value(row.get(excel_col))

            mapped["Quantity"] = to_decimal(row.get("Quantity"))
            mapped["Rate"] = to_decimal(row.get("Rate"))
            mapped["TotalCost"] = to_decimal(row.get("TotalCost"))

            l2_key = str(mapped.get("L2Code") or "").strip().upper() or "__NO_L2__"
            next_order = display_order_by_l2.get(l2_key, 0) + 1
            display_order_by_l2[l2_key] = next_order
            mapped["DisplayOrder"] = next_order

            mapped["RowType"] = infer_l3_row_type(
                mapped.get("Quantity"),
                mapped.get("Unit"),
                mapped.get("Rate"),
                mapped.get("TotalCost"),
            )
            rows.append(mapped)
        return rows


class AdjustmentsStager(SheetStager):
    table_key = "Adjustments"

    def build_rows(
        self, load_batch_id: str, source_file: str, df: pd.DataFrame, **kwargs
    ) -> list[dict]:
        rows = []
        for idx, row in self.iter_data_rows(df):
            mapped = {
                "LoadBatchID": load_batch_id,
                "RowNum": int(idx) + 2,
                "SourceFileName": source_file,
            }
            for excel_col, db_col in COLUMN_MAPS["Adjustments"].items():
                mapped[db_col] = clean_value(row.get(excel_col))

            mapped["Amount"] = to_decimal(row.get("Amount"))
            mapped["RatePercent"] = to_decimal(row.get("RatePercent"))
            mapped["AppliedToBase"] = to_bit(row.get("AppliedToBase"))
            mapped["IncludedInComparison"] = to_bit(row.get("IncludedInComparison"))
            rows.append(mapped)
        return rows
