"""
Characterization tests for excel_file_ingestion.

Freeze today's normalized DataFrames and staged row sets from the sample
workbook. Refactors must reproduce these goldens exactly unless --update-golden
is used intentionally.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from ingestion_engine import excel_file_ingestion as ing
from ingestion_engine.config import IngestionConfig, clear_ingestion_config_cache
from ingestion_engine.workbook import read_workbook

from .helpers import (
    CANONICAL_DATAFRAMES,
    DATAFRAME_GOLDEN_DIR,
    FIXED_LOAD_BATCH_ID,
    FIXED_SOURCE_FILE,
    SAMPLE_WORKBOOK,
    STAGED_GOLDEN_DIR,
    assert_or_update_golden,
    dataframe_to_records,
    rows_to_records,
)


def _test_config(**overrides) -> IngestionConfig:
    """Config that never touches a real DB during characterization."""
    base = {
        "process_adjustments": False,
        "debug_level2": False,
        "sql_server": "TEST_SERVER",
        "sql_db": "TEST_DB",
    }
    base.update(overrides)
    return IngestionConfig(**base)


@pytest.fixture(scope="module")
def sample_dataframes():
    assert SAMPLE_WORKBOOK.exists(), f"Missing sample workbook: {SAMPLE_WORKBOOK}"
    clear_ingestion_config_cache()
    with patch(
        "ingestion_engine.config.get_ingestion_config",
        return_value=_test_config(),
    ):
        dfs = read_workbook(io.BytesIO(SAMPLE_WORKBOOK.read_bytes()))
    clear_ingestion_config_cache()
    yield dfs


def test_sample_workbook_normalized_dataframes(sample_dataframes, update_golden):
    for name in CANONICAL_DATAFRAMES:
        assert name in sample_dataframes, f"Missing dataframe '{name}'"
        actual = dataframe_to_records(sample_dataframes[name])
        path = DATAFRAME_GOLDEN_DIR / f"{name}.json"
        assert_or_update_golden(path, actual, update=update_golden)


def test_sample_workbook_staged_rows(sample_dataframes, update_golden):
    captured: dict[str, list] = {}

    def fake_insert(_conn, table_name, rows):
        captured[table_name] = rows_to_records(rows)

    # Avoid live SQL while still exercising staging mappers.
    with (
        patch.object(ing, "insert_dataframe_rows", side_effect=fake_insert),
        patch.object(ing, "get_connection", return_value=MagicMock()),
        patch.object(ing, "_get_decimal_metadata", return_value={}),
        patch.object(ing, "fetch_all", return_value=[]),
        patch.object(ing, "resolve_sector_code", side_effect=lambda v: v),
        patch.object(ing, "log_validation_error"),
        patch.object(ing, "get_ingestion_config", return_value=_test_config()),
    ):
        ing.stage_all_sheets(
            load_batch_id=FIXED_LOAD_BATCH_ID,
            source_file=FIXED_SOURCE_FILE,
            dataframes=sample_dataframes,
        )

    expected_tables = [
        "stg.ProjectInformation",
        "stg.ProjectTenderer",
        "stg.ProjectQuants",
        "stg.ElementQuants_L2",
        "stg.Level2",
        "stg.LineItem_L3",
    ]
    for table in expected_tables:
        assert table in captured, f"Missing staged table '{table}'"
        path = STAGED_GOLDEN_DIR / f"{table.split('.', 1)[1]}.json"
        assert_or_update_golden(path, captured[table], update=update_golden)
