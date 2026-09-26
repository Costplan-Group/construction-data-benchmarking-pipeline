"""Run all sheet stagers for a load batch."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ingestion_engine.config import get_ingestion_config
from ingestion_engine.staging.stagers import (
    AdjustmentsStager,
    ElementQuantsL2Stager,
    Level2Stager,
    LineItemL3Stager,
    ProjectInformationStager,
    ProjectQuantsStager,
    ProjectTendererStager,
)
from ingestion_engine.workbook.normalizers.project_quants import extract_gifa_from_project_quants


def stage_all_sheets(
    load_batch_id: str,
    source_file: str,
    dataframes: dict,
    *,
    connection_factory: Callable[[], Any],
    insert_rows: Callable,
    get_decimal_metadata: Callable[[str], dict],
    log_validation_error: Callable | None = None,
    resolve_sector_code: Callable | None = None,
    fetch_all: Callable | None = None,
    conn=None,
    commit: bool = True,
) -> None:
    stager_kwargs = {
        "connection_factory": connection_factory,
        "insert_rows": insert_rows,
        "get_decimal_meta": get_decimal_metadata,
        "log_validation_error": log_validation_error,
        "resolve_sector_code": resolve_sector_code,
        "fetch_all": fetch_all,
    }

    fallback_gifa = extract_gifa_from_project_quants(dataframes.get("ProjectQuants"))

    def _run(stager, df, **extra):
        if conn is not None:
            stager.stage(conn, load_batch_id, source_file, df, commit=commit, **extra)
        else:
            local_conn = connection_factory()
            try:
                stager.stage(local_conn, load_batch_id, source_file, df, commit=True, **extra)
            finally:
                local_conn.close()

    _run(
        ProjectInformationStager(**stager_kwargs),
        dataframes["ProjectInformation"],
        fallback_gifa=fallback_gifa,
    )
    _run(ProjectTendererStager(**stager_kwargs), dataframes["ProjectInformation"])
    _run(ProjectQuantsStager(**stager_kwargs), dataframes["ProjectQuants"])
    _run(ElementQuantsL2Stager(**stager_kwargs), dataframes["ElementQuants_L2"])
    _run(Level2Stager(**stager_kwargs), dataframes["Level2"])
    _run(LineItemL3Stager(**stager_kwargs), dataframes["LineItem_L3"])
    if get_ingestion_config().process_adjustments and "Adjustments" in dataframes:
        _run(AdjustmentsStager(**stager_kwargs), dataframes["Adjustments"])
