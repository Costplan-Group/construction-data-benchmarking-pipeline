"""L1/L2 code formatting helpers."""

from __future__ import annotations

from decimal import Decimal

from ingestion_engine.coercion import clean_value


def format_code_text(value) -> str | None:
    cv = clean_value(value)
    if cv is None:
        return None
    text = str(cv).strip()
    try:
        d = Decimal(text)
    except Exception:
        return text
    return format(d.normalize(), "f")


def split_l1_l2_code(ref_value) -> tuple[str | None, str | None]:
    code = format_code_text(ref_value)
    if code is None:
        return None, None
    if "." not in code:
        return code, None
    major, minor = code.split(".", 1)
    if minor.strip("0") == "":
        return f"{major}.0", None
    return f"{major}.0", code
