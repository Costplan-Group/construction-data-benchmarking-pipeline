"""ProjectInformation sheet normalizer."""

from __future__ import annotations

import re

import pandas as pd

from ingestion_engine.coercion import clean_value, normalize_text
from ingestion_engine.workbook.normalizers.base import SheetNormalizer


def _canonical_project_info_field(key_text: str) -> list[str]:
    text = (key_text or "").strip()
    if not text:
        return []

    key_map = {
        "projectid": "ProjectID",
        "projectnumber": "ProjectID",
        "projectno": "ProjectID",
        "projectref": "ProjectID",
        "projectname": "ProjectName",
        "clientname": "ClientName",
        "location": "LocationLabel",
        "locationlabel": "LocationLabel",
        "region": "LocationLabel",
        "sector": "SectorCode",
        "sectorcode": "SectorCode",
        "coststage": "CostStage",
        "budgetstage": "BudgetStage",
        "contractorname": "SelectedContractor",
        "selectedcontractor": "SelectedContractor",
        "datastatus": "DataStatus",
        "demolition": "Demolition",
        "newbuild": "NewBuild",
        "refurbishment": "Refurbishment",
        "horizontalextension": "HorizontalExtension",
        "verticalextension": "VerticalExtension",
        "basement": "Basement",
        "asbestos": "Asbestos",
        "contamination": "Contamination",
        "speclevel": "SpecLevel",
        "specificationlevel": "SpecLevel",
        "sitetype": "SiteType",
        "nrofstoreys": "NrOfStoreys",
        "noofstoreys": "NrOfStoreys",
        "numberofstoreys": "NrOfStoreys",
        "totalheightgroundtoroof": "TotalHeightGroundToRoof",
        "basementarea": "BasementArea",
        "basementheight": "BasementHeight",
        "complexityrating": "ComplexityRating",
        "accessconstraints": "AccessConstraints",
        "occupied": "Occupied",
        "basedate": "BaseDate",
        "currency": "Currency",
        "programmelengthinweeks": "ProgrammeLengthInWeeks",
        "programmetype": "ProgrammeType",
        "gifa": "GIFA",
        "notes": "Notes",
    }

    n = normalize_text(text)
    fields: list[str] = []

    exact = key_map.get(n)
    if exact:
        fields.append(exact)

    if "selectedcontractor" in n and "SelectedContractor" not in fields:
        fields.append("SelectedContractor")

    contractor_match = re.match(r"^contractor\s*(\d+)\b", text, flags=re.IGNORECASE)
    if contractor_match:
        label = f"Contractor {int(contractor_match.group(1))}"
        if label not in fields:
            fields.append(label)

    return fields


class ProjectInformationNormalizer(SheetNormalizer):
    canonical_name = "ProjectInformation"

    def normalize(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        wide_rename = {}
        for col in df.columns:
            col_text = str(col).strip()
            n = normalize_text(col_text)
            if n in {"projectid", "projectnumber", "projectno", "projectref"}:
                wide_rename[col] = "ProjectID"
            elif "selectedcontractor" in n or n in {"contractorname", "selectedcontractor"}:
                wide_rename[col] = "SelectedContractor"
            else:
                contractor_match = re.match(r"^contractor\s*(\d+)\b", col_text, flags=re.IGNORECASE)
                if contractor_match and "selected" in col_text.casefold():
                    wide_rename[col] = "SelectedContractor"
        if wide_rename:
            df = df.rename(columns=wide_rename)

        if "ProjectID" in df.columns and "ProjectName" in df.columns:
            if "SelectedContractor" not in df.columns:
                for col in list(df.columns):
                    col_text = str(col).strip()
                    if "selected" in col_text.casefold() and re.match(
                        r"^contractor\s*\d+\b", col_text, flags=re.IGNORECASE
                    ):
                        df = df.rename(columns={col: "SelectedContractor"})
                        break
            return df

        cols = list(df.columns)
        if len(cols) < 2:
            return df
        key_col, val_col = cols[0], cols[1]

        out: dict[str, object] = {}
        for _, row in df.iterrows():
            k = clean_value(row.get(key_col))
            v = clean_value(row.get(val_col))
            if k is None:
                continue
            key_text = str(k).strip()
            for canonical in _canonical_project_info_field(key_text):
                if v is not None or canonical not in out:
                    out[canonical] = v

        return pd.DataFrame([out]) if out else df


def is_placeholder_tenderer_name(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    low = text.casefold()
    if low in {"tbd", "n/a", "na", "-", "--"}:
        return True
    if re.match(r"^insert\s+contractor\b", low):
        return True
    return False


def extract_tenderers_from_project_information_df(
    project_info_df: pd.DataFrame,
) -> list[tuple[str, str]]:
    if project_info_df is None or project_info_df.empty:
        return []

    contractor_label_pattern = re.compile(r"^Contractor\s*(\d+)\b", re.IGNORECASE)
    seen: set[str] = set()
    results: list[tuple[str, str]] = []

    for _, row in project_info_df.iterrows():
        for col in project_info_df.columns:
            col_name = str(col).strip()
            m = contractor_label_pattern.match(col_name)
            if not m:
                continue
            raw_val = clean_value(row.get(col))
            name = str(raw_val).strip() if raw_val is not None else ""
            if is_placeholder_tenderer_name(name):
                continue
            dedupe_key = name.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            label = f"Contractor {int(m.group(1))}"
            results.append((label, name))
    return results
