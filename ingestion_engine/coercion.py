"""Pure-ish value conversion helpers for Excel ingestion."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


def clean_value(value):
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        value = value.strip()
        return value if value != "" else None

    return value


def to_int(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def to_decimal(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def to_bit(value):
    value = clean_value(value)
    if value is None:
        return None

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return 1 if value else 0

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return 1
    if text in {"0", "false", "no", "n"}:
        return 0
    return None


def unescape_html_text(value) -> str:
    """Decode HTML entities safely, including double-encoded text like '&amp;amp;'."""
    text = str(value)
    previous = None
    current = text
    for _ in range(3):
        if current == previous:
            break
        previous = current
        current = html.unescape(current)
    return current


def normalize_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", unescape_html_text(value).strip().lower())


def resolve_sector_code(
    value: str | None,
    *,
    connection_factory: Callable[[], Any] | None = None,
) -> str | None:
    """
    Resolve workbook sector text to dbo.DimSector.SectorCode.
    connection_factory defaults to ingestion get_connection when omitted.
    """
    raw = clean_value(value)
    if raw is None:
        return None

    text = str(raw).strip()
    if connection_factory is None:
        from ingestion_engine.connection import get_connection

        connection_factory = get_connection

    conn = connection_factory()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 SectorCode
            FROM dbo.DimSector
            WHERE UPPER(LTRIM(RTRIM(SectorCode))) = UPPER(LTRIM(RTRIM(?)))
               OR UPPER(LTRIM(RTRIM(SectorName))) = UPPER(LTRIM(RTRIM(?)))
            ORDER BY SectorKey
            """,
            (text, text),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip()
        return text
    finally:
        conn.close()
