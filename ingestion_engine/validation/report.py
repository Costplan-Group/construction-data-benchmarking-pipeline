"""Ordered workbook validators writing through ValidationErrorRepository."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

import pandas as pd

from ingestion_engine import project_attributes
from ingestion_engine.coercion import clean_value, to_decimal
from ingestion_engine.schema import REQUIRED_COLUMNS
from ingestion_engine.workbook.aliases import source_sheet_name

if TYPE_CHECKING:
    from backend.app.repositories.validation_error import ValidationErrorRepository


class ValidationReport:
    """Collects validation outcomes (error count comes from repository)."""

    def __init__(self):
        self.ran_validators: list[str] = []


class WorkbookValidator(ABC):
    @abstractmethod
    def validate(
        self,
        load_batch_id: str,
        dataframes: dict[str, pd.DataFrame],
        *,
        error_repo: ValidationErrorRepository,
        report: ValidationReport,
    ) -> None: ...


class RequiredColumnsValidator(WorkbookValidator):
    def validate(
        self,
        load_batch_id: str,
        dataframes: dict[str, pd.DataFrame],
        *,
        error_repo: ValidationErrorRepository,
        report: ValidationReport,
    ) -> None:
        resolved_sheets = dataframes.get("_resolved_sheets") or {}
        for sheet_name, df in dataframes.items():
            if sheet_name not in REQUIRED_COLUMNS:
                continue
            display_name = resolved_sheets.get(sheet_name) or source_sheet_name(df, sheet_name)
            if sheet_name == "Level2":
                display_name = resolved_sheets.get("SUMMARY") or source_sheet_name(df, "SUMMARY")
            for col in REQUIRED_COLUMNS[sheet_name]:
                if col not in df.columns:
                    error_repo.log(
                        load_batch_id=load_batch_id,
                        sheet_name=display_name,
                        column_name=col,
                        error_type="MISSING_COLUMN",
                        error_message=f"Missing required column '{col}' in sheet '{display_name}'",
                        use_row_data_column=True,
                    )
        report.ran_validators.append("RequiredColumnsValidator")


class RowLevelValidator(WorkbookValidator):
    def validate(
        self,
        load_batch_id: str,
        dataframes: dict[str, pd.DataFrame],
        *,
        error_repo: ValidationErrorRepository,
        report: ValidationReport,
    ) -> None:
        resolved_sheets = dataframes.get("_resolved_sheets") or {}

        pi_df = dataframes["ProjectInformation"]
        pi_sheet = resolved_sheets.get("ProjectInformation") or source_sheet_name(
            pi_df, "ProjectInformation"
        )
        non_blank_rows = pi_df.dropna(how="all")
        if len(non_blank_rows) != 1:
            error_repo.log(
                load_batch_id,
                pi_sheet,
                error_type="ROW_COUNT",
                error_message=f"{pi_sheet} should contain exactly 1 populated row",
                row_data={"observed_non_blank_rows": int(len(non_blank_rows))},
                use_row_data_column=True,
            )

        lvl2_df = dataframes["Level2"]
        lvl2_sheet = resolved_sheets.get("SUMMARY") or source_sheet_name(lvl2_df, "SUMMARY")
        if "TotalCost" in lvl2_df.columns:
            for idx, val in enumerate(lvl2_df["TotalCost"], start=2):
                if clean_value(val) is not None and to_decimal(val) is None:
                    error_repo.log(
                        load_batch_id,
                        lvl2_sheet,
                        row_num=idx,
                        column_name="TotalCost",
                        error_type="INVALID_NUMBER",
                        error_message=f"Invalid TotalCost value: {val}",
                        row_data={
                            "L1Code": clean_value(lvl2_df.iloc[idx - 2].get("L1Code"))
                            if idx - 2 < len(lvl2_df)
                            else None,
                            "L1Name": clean_value(lvl2_df.iloc[idx - 2].get("L1Name"))
                            if idx - 2 < len(lvl2_df)
                            else None,
                            "L2Code": clean_value(lvl2_df.iloc[idx - 2].get("L2Code"))
                            if idx - 2 < len(lvl2_df)
                            else None,
                            "L2Name": clean_value(lvl2_df.iloc[idx - 2].get("L2Name"))
                            if idx - 2 < len(lvl2_df)
                            else None,
                            "Rate": clean_value(lvl2_df.iloc[idx - 2].get("Rate"))
                            if idx - 2 < len(lvl2_df)
                            else None,
                            "TotalCost": clean_value(val),
                        },
                        use_row_data_column=True,
                    )

        l3_df = dataframes["LineItem_L3"]
        l3_sheet = source_sheet_name(l3_df, "Level 3 sheets")
        allowed_row_types = {"ITEM", "HEADING", "SUBTOTAL"}
        if "RowType" in l3_df.columns:
            for idx, val in enumerate(l3_df["RowType"], start=2):
                cv = clean_value(val)
                if cv is not None and str(cv).upper() not in allowed_row_types:
                    error_repo.log(
                        load_batch_id,
                        l3_sheet,
                        row_num=idx,
                        column_name="RowType",
                        error_type="DOMAIN",
                        error_message=(
                            f"Invalid RowType '{val}'. Allowed: ITEM, HEADING, SUBTOTAL"
                        ),
                        row_data={
                            "L2Code": clean_value(l3_df.iloc[idx - 2].get("L2Code"))
                            if idx - 2 < len(l3_df)
                            else None,
                            "L2Name": clean_value(l3_df.iloc[idx - 2].get("L2Name"))
                            if idx - 2 < len(l3_df)
                            else None,
                            "ItemDescription": clean_value(
                                l3_df.iloc[idx - 2].get("ItemDescription")
                            )
                            if idx - 2 < len(l3_df)
                            else None,
                            "Quantity": clean_value(l3_df.iloc[idx - 2].get("Quantity"))
                            if idx - 2 < len(l3_df)
                            else None,
                            "Unit": clean_value(l3_df.iloc[idx - 2].get("Unit"))
                            if idx - 2 < len(l3_df)
                            else None,
                            "Rate": clean_value(l3_df.iloc[idx - 2].get("Rate"))
                            if idx - 2 < len(l3_df)
                            else None,
                            "TotalCost": clean_value(l3_df.iloc[idx - 2].get("TotalCost"))
                            if idx - 2 < len(l3_df)
                            else None,
                            "RowType": clean_value(val),
                        },
                        use_row_data_column=True,
                    )

        pq_df = dataframes["ProjectQuants"]
        pq_sheet = resolved_sheets.get("ProjectQuants") or source_sheet_name(pq_df, "ProjectQuants")
        if "Qty" in pq_df.columns:
            for idx, val in enumerate(pq_df["Qty"], start=2):
                if clean_value(val) is not None and to_decimal(val) is None:
                    error_repo.log(
                        load_batch_id,
                        pq_sheet,
                        row_num=idx,
                        column_name="Qty",
                        error_type="INVALID_NUMBER",
                        error_message=f"Invalid Qty value: {val}",
                        row_data={
                            "ProjectQuantCode": clean_value(
                                pq_df.iloc[idx - 2].get("ProjectQuantCode")
                            )
                            if idx - 2 < len(pq_df)
                            else None,
                            "ProjectQuantName": clean_value(
                                pq_df.iloc[idx - 2].get("ProjectQuantName")
                            )
                            if idx - 2 < len(pq_df)
                            else None,
                            "Qty": clean_value(val),
                            "Unit": clean_value(pq_df.iloc[idx - 2].get("Unit"))
                            if idx - 2 < len(pq_df)
                            else None,
                        },
                        use_row_data_column=True,
                    )

        report.ran_validators.append("RowLevelValidator")


class ProjectAttributeValidator(WorkbookValidator):
    """Domain checks for the DimProject attributes on the ProjectInformation row.

    Blank values (missing label, empty cell) are allowed; a non-blank value outside
    the allowed list or range is an error. 0 is a value, not a blank.
    """

    def validate(
        self,
        load_batch_id: str,
        dataframes: dict[str, pd.DataFrame],
        *,
        error_repo: ValidationErrorRepository,
        report: ValidationReport,
    ) -> None:
        pi_df = dataframes.get("ProjectInformation")
        if pi_df is None or pi_df.empty:
            report.ran_validators.append("ProjectAttributeValidator")
            return

        resolved_sheets = dataframes.get("_resolved_sheets") or {}
        pi_sheet = resolved_sheets.get("ProjectInformation") or source_sheet_name(
            pi_df, "ProjectInformation"
        )
        row = pi_df.iloc[0]

        for field in project_attributes.VALIDATED_FIELDS:
            if field not in pi_df.columns:
                continue
            raw = row.get(field)
            error = project_attributes.attribute_error(field, raw)
            if error is None:
                continue
            error_type, message = error
            error_repo.log(
                load_batch_id,
                pi_sheet,
                column_name=field,
                error_type=error_type,
                error_message=message,
                row_data={field: clean_value(raw)},
                use_row_data_column=True,
            )

        report.ran_validators.append("ProjectAttributeValidator")


_DEFAULT_VALIDATORS: list[WorkbookValidator] = [
    RequiredColumnsValidator(),
    RowLevelValidator(),
    ProjectAttributeValidator(),
]


def validate_workbook_data(
    load_batch_id: str,
    dataframes: dict,
    *,
    error_repo: ValidationErrorRepository | None = None,
    log_fn: Callable | None = None,
) -> ValidationReport:
    """
    Run ordered validators. Uses ValidationErrorRepository when provided;
    otherwise falls back to log_fn (façade log_validation_error).
    """
    report = ValidationReport()
    if error_repo is None:
        if log_fn is None:
            raise ValueError("validate_workbook_data requires error_repo or log_fn")

        class _Adapter:
            def log(self, load_batch_id, sheet_name=None, **kwargs):
                kwargs.pop("use_row_data_column", None)
                log_fn(load_batch_id, sheet_name=sheet_name, **kwargs)

        error_repo = _Adapter()  # type: ignore[assignment]

    for validator in _DEFAULT_VALIDATORS:
        validator.validate(load_batch_id, dataframes, error_repo=error_repo, report=report)
    return report
