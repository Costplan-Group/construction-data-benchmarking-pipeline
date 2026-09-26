"""
Characterization / golden-master helpers for ingestion refactor safety.

Capture today's normalized DataFrames and staged row sets from the sample
workbook, then assert future runs match exactly.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_WORKBOOK = REPO_ROOT / "sample_data" / "DEMO_Tender_Comparison_Workbook.xlsx"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
DATAFRAME_GOLDEN_DIR = GOLDEN_DIR / "dataframes"
STAGED_GOLDEN_DIR = GOLDEN_DIR / "staged_rows"

CANONICAL_DATAFRAMES = [
    "ProjectInformation",
    "ProjectQuants",
    "ElementQuants_L2",
    "Level2",
    "LineItem_L3",
]

FIXED_LOAD_BATCH_ID = "00000000-0000-0000-0000-000000000001"
FIXED_SOURCE_FILE = "DEMO_Tender_Comparison_Workbook.xlsx"


def json_ready(value: Any) -> Any:
    """Normalize values for stable JSON comparison."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        # Avoid binary float drift in goldens; prefer decimal-like strings.
        return format(Decimal(str(value)), "f")
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if pd.isna(value):
        return None
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    return value


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    drop = [c for c in df.columns if str(c).startswith("__")]
    clean = df.drop(columns=drop, errors="ignore").copy()
    records: list[dict[str, Any]] = []
    for _, row in clean.iterrows():
        records.append({str(k): json_ready(v) for k, v in row.to_dict().items()})
    return records


def rows_to_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(k): json_ready(v) for k, v in row.items()} for row in rows]


def read_golden(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_golden(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def assert_or_update_golden(path: Path, actual: Any, update: bool) -> None:
    if update or not path.exists():
        write_golden(path, actual)
        return
    expected = read_golden(path)
    assert actual == expected, (
        f"Characterization drift vs {path.relative_to(REPO_ROOT)}.\n"
        "If the change is intentional, re-run with --update-golden."
    )
