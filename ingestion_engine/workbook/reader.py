"""Read and normalize Excel workbooks into canonical dataframes."""

from __future__ import annotations

import io
import re

import pandas as pd

from ingestion_engine.coercion import unescape_html_text as _unescape_html_text
from ingestion_engine.contractor import ContractorSelector
from ingestion_engine.schema import required_base_sheets
from ingestion_engine.workbook.aliases import (
    SHEET_ALIASES,
    all_base_sheet_names_and_aliases,
    resolve_sheet_name,
)
from ingestion_engine.workbook.normalizers import (
    AdjustmentsNormalizer,
    ElementQuantsNormalizer,
    L3SheetNormalizer,
    ProjectInformationNormalizer,
    ProjectQuantsNormalizer,
    SummaryNormalizer,
)
from ingestion_engine.workbook.normalizers.summary import extract_summary_tenderer_totals


class WorkbookReader:
    def __init__(self, contractor_selector: ContractorSelector | None = None):
        self.contractor = contractor_selector or ContractorSelector()
        self._pi = ProjectInformationNormalizer(self.contractor)
        self._pq = ProjectQuantsNormalizer(self.contractor)
        self._eq = ElementQuantsNormalizer(self.contractor)
        self._adj = AdjustmentsNormalizer(self.contractor)
        self._summary = SummaryNormalizer(self.contractor)
        self._l3 = L3SheetNormalizer(self.contractor)

    def read(self, file_like: io.BytesIO) -> dict[str, pd.DataFrame]:
        xls = pd.ExcelFile(file_like, engine="openpyxl")

        resolved_sheets: dict[str, str] = {}
        missing_sheets = []
        base_sheets = required_base_sheets()
        for canonical in base_sheets:
            actual = resolve_sheet_name(canonical, xls.sheet_names)
            if actual is None:
                missing_sheets.append(canonical)
            else:
                resolved_sheets[canonical] = actual
        if missing_sheets:
            alias_hint = {name: SHEET_ALIASES.get(name, [name]) for name in missing_sheets}
            raise ValueError(
                f"Missing required sheets: {missing_sheets}. Accepted names by sheet: {alias_hint}"
            )

        l3_sheet_name_pattern = re.compile(r"^\s*([A-Za-z]*\d+(?:\.\d+)*)\s+(.+?)\s*$")
        base_sheet_keys = all_base_sheet_names_and_aliases()
        resolved_actual_names = {v.strip().casefold() for v in resolved_sheets.values()}
        l3_sheets: list[tuple[str, str]] = []
        for sheet in xls.sheet_names:
            actual_name = str(sheet)
            decoded_name = _unescape_html_text(sheet).strip()
            if (
                actual_name.strip().casefold() in resolved_actual_names
                or decoded_name.casefold() in base_sheet_keys
                or actual_name.strip().casefold() in base_sheet_keys
            ):
                continue
            if l3_sheet_name_pattern.match(decoded_name):
                l3_sheets.append((actual_name, decoded_name))
        if not l3_sheets:
            raise ValueError(
                "Missing Level 3 sheet(s). Expected at least one sheet named like '<L2Code> <L2Name>'."
            )

        dataframes: dict[str, pd.DataFrame] = {}
        for sheet in base_sheets:
            actual_sheet = resolved_sheets[sheet]
            df = pd.read_excel(xls, sheet_name=actual_sheet, engine="openpyxl")
            df.columns = [str(c).strip() for c in df.columns]
            if sheet == "ProjectInformation":
                df = self._pi.normalize(df)
            elif sheet == "ProjectQuants":
                df = self._pq.normalize(df)
            elif sheet == "ElementQuants_L2":
                df = self._eq.normalize(df)
            elif sheet == "Adjustments":
                df = self._adj.normalize(df)
            if isinstance(df, pd.DataFrame):
                df.attrs["source_sheet_name"] = actual_sheet
            dataframes[sheet] = df

        selected_contractor = self.contractor.get_selected_contractor(
            dataframes.get("ProjectInformation")
        )
        if not selected_contractor:
            selected_contractor = self.contractor.detect_from_workbook(xls)

        l3_frames = []
        for actual_sheet_name, decoded_sheet_name in l3_sheets:
            raw_l3_df = pd.read_excel(
                xls,
                sheet_name=actual_sheet_name,
                engine="openpyxl",
                header=None,
            )

            m = l3_sheet_name_pattern.match(decoded_sheet_name)
            l2_code_from_sheet = m.group(1).strip() if m else None
            l2_name_from_sheet = _unescape_html_text(m.group(2)).strip() if m else None

            try:
                df = self._l3.normalize(
                    raw_l3_df,
                    l2_code=l2_code_from_sheet,
                    l2_name=l2_name_from_sheet,
                    selected_contractor=selected_contractor,
                )
            except ValueError:
                continue
            l3_frames.append(df)

        dataframes["LineItem_L3"] = (
            pd.concat(l3_frames, ignore_index=True) if l3_frames else pd.DataFrame()
        )
        dataframes["LineItem_L3"].attrs["source_sheet_name"] = "Level 3 sheets"

        summary_actual = resolved_sheets["SUMMARY"]
        summary_raw = pd.read_excel(xls, sheet_name=summary_actual, engine="openpyxl", header=None)
        summary_df = self._summary.normalize(summary_raw, selected_contractor=selected_contractor)
        summary_df.attrs["source_sheet_name"] = summary_actual
        dataframes["Level2"] = summary_df
        summary_tenderer_totals = extract_summary_tenderer_totals(summary_raw)
        if "ProjectInformation" in dataframes:
            dataframes["ProjectInformation"].attrs["summary_tenderer_totals"] = pd.DataFrame(
                summary_tenderer_totals
            )

        dataframes["_resolved_sheets"] = resolved_sheets
        return dataframes


def read_workbook(file_like: io.BytesIO) -> dict[str, pd.DataFrame]:
    return WorkbookReader().read(file_like)
