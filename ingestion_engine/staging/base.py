"""Base sheet stager with shared decimal coercion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pandas as pd

from ingestion_engine.row_utils import is_effectively_blank_row
from ingestion_engine.schema import STAGING_TABLES
from ingestion_engine.staging.decimal_coerce import coerce_decimal_to_precision_scale
from ingestion_engine.staging.insert import get_decimal_metadata, insert_dataframe_rows


class SheetStager(ABC):
    table_key: str

    def __init__(
        self,
        *,
        connection_factory: Callable[[], Any],
        insert_rows: Callable = insert_dataframe_rows,
        get_decimal_meta: Callable[[str], dict[str, tuple[int, int]]] | None = None,
        log_validation_error: Callable | None = None,
        resolve_sector_code: Callable | None = None,
        fetch_all: Callable | None = None,
    ):
        self.connection_factory = connection_factory
        self.insert_rows = insert_rows
        self._get_decimal_meta = get_decimal_meta or (
            lambda table: get_decimal_metadata(table, connection_factory)
        )
        self.log_validation_error = log_validation_error
        self.resolve_sector_code = resolve_sector_code
        self.fetch_all = fetch_all

    @property
    def table_name(self) -> str:
        return STAGING_TABLES[self.table_key]

    def coerce_row_decimals(
        self,
        mapped: dict,
        decimal_cols: tuple[str, ...],
        decimal_meta: dict[str, tuple[int, int]],
    ) -> dict:
        for dec_col in decimal_cols:
            dec_val = mapped.get(dec_col)
            if dec_val is None or not isinstance(dec_val, Decimal):
                continue
            if dec_col not in decimal_meta:
                continue
            precision, scale = decimal_meta[dec_col]
            mapped[dec_col] = coerce_decimal_to_precision_scale(dec_val, precision, scale)
        return mapped

    def stage(
        self,
        conn,
        load_batch_id: str,
        source_file: str,
        df: pd.DataFrame,
        *,
        commit: bool = True,
        **kwargs,
    ) -> None:
        rows = self.build_rows(load_batch_id, source_file, df, **kwargs)
        if not rows:
            return
        if commit:
            self.insert_rows(conn, self.table_name, rows)
        else:
            self.insert_rows(conn, self.table_name, rows, commit=False)

    @abstractmethod
    def build_rows(
        self,
        load_batch_id: str,
        source_file: str,
        df: pd.DataFrame,
        **kwargs,
    ) -> list[dict]: ...

    def iter_data_rows(self, df: pd.DataFrame):
        for idx, row in df.iterrows():
            if is_effectively_blank_row(row):
                continue
            yield idx, row
