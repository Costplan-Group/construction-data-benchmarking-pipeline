"""Column maps, required columns, and staging table names for Excel ingestion."""

from __future__ import annotations

from ingestion_engine.config import get_ingestion_config

_REQUIRED_BASE_SHEETS_CORE = [
    "ProjectInformation",
    "ProjectQuants",
    "ElementQuants_L2",
    "SUMMARY",
]


def required_base_sheets() -> list[str]:
    """Canonical base sheets; Adjustments included when PROCESS_ADJUSTMENTS is enabled."""
    sheets = list(_REQUIRED_BASE_SHEETS_CORE)
    if get_ingestion_config().process_adjustments:
        sheets.append("Adjustments")
    return sheets


# Back-compat alias for callers that still import REQUIRED_BASE_SHEETS.
REQUIRED_BASE_SHEETS = _REQUIRED_BASE_SHEETS_CORE

COLUMN_MAPS = {
    "ProjectInformation": {
        "ProjectID": "ProjectID",
        "ProjectName": "ProjectName",
        "ClientName": "ClientName",
        "LocationLabel": "LocationLabel",
        "SectorCode": "SectorCode",
        "CostStage": "CostStage",
        "BudgetStage": "BudgetStage",
        "SelectedContractor": "SelectedContractor",
        "DataStatus": "DataStatus",
        "Demolition": "Demolition",
        "NewBuild": "NewBuild",
        "Refurbishment": "Refurbishment",
        "HorizontalExtension": "HorizontalExtension",
        "VerticalExtension": "VerticalExtension",
        "Basement": "Basement",
        "Asbestos": "Asbestos",
        "Contamination": "Contamination",
        "SpecLevel": "SpecLevel",
        "SiteType": "SiteType",
        "NrOfStoreys": "NrOfStoreys",
        "TotalHeightGroundToRoof": "TotalHeightGroundToRoof",
        "BasementArea": "BasementArea",
        "BasementHeight": "BasementHeight",
        "ComplexityRating": "ComplexityRating",
        "AccessConstraints": "AccessConstraints",
        "Occupied": "Occupied",
        "BaseDate": "BaseDate",
        "Currency": "Currency",
        "ProgrammeLengthInWeeks": "ProgrammeLengthInWeeks",
        "ProgrammeType": "ProgrammeType",
        "GIFA": "GIFA",
        "Notes": "Notes",
    },
    "ProjectQuants": {
        "ProjectQuantCode": "ProjectQuantCode",
        "ProjectQuantName": "ProjectQuantName",
        "Qty": "Qty",
        "Unit": "Unit",
        "Comment": "Comment",
    },
    "ElementQuants_L2": {
        "L2Code": "L2Code",
        "L2Name": "L2Name",
        "Qty": "Qty",
        "Unit": "Unit",
        "Comment": "Comment",
    },
    "Level2": {
        "L1Code": "L1Code",
        "L1Name": "L1Name",
        "L2Code": "L2Code",
        "L2Name": "L2Name",
        "Rate": "Rate",
        "TotalCost": "TotalCost",
    },
    "LineItem_L3": {
        "L2Code": "L2Code",
        "L2Name": "L2Name",
        "LineID": "LineID",
        "DisplayOrder": "DisplayOrder",
        "ItemDescription": "ItemDescription",
        "Qty": "Quantity",
        "Unit": "Unit",
        "Rate": "Rate",
        "Total": "TotalCost",
        "RowType": "RowType",
    },
    "Adjustments": {
        "AdjCategory": "AdjCategory",
        "AdjSubType": "AdjSubType",
        "Amount": "Amount",
        "Method": "Method",
        "RatePercent": "RatePercent",
        "AppliedToBase": "AppliedToBase",
        "IncludedInComparison": "IncludedInComparison",
    },
}

REQUIRED_COLUMNS = {
    "ProjectInformation": [
        "ProjectID",
        "ProjectName",
        "LocationLabel",
        "SectorCode",
        "CostStage",
        "SelectedContractor",
    ],
    "ProjectQuants": ["ProjectQuantName", "Qty", "Unit"],
    "ElementQuants_L2": ["L2Code", "QuantTypeCode", "Qty"],
    "Level2": ["L2Code", "L2Name", "TotalCost"],
    "LineItem_L3": ["L2Code", "ItemDescription", "RowType"],
    "Adjustments": ["AdjCategory", "Amount"],
}

STAGING_TABLES = {
    "ProjectInformation": "stg.ProjectInformation",
    "ProjectTenderer": "stg.ProjectTenderer",
    "ProjectQuants": "stg.ProjectQuants",
    "ElementQuants_L2": "stg.ElementQuants_L2",
    "Level2": "stg.Level2",
    "LineItem_L3": "stg.LineItem_L3",
    "Adjustments": "stg.Adjustments",
}
