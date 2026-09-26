"""Workbook sheet name aliases and resolution."""

from __future__ import annotations

from ingestion_engine.coercion import unescape_html_text as _unescape_html_text
from ingestion_engine.schema import required_base_sheets

SHEET_ALIASES = {
    "ProjectInformation": [
        "ProjectInformation",
        "Project Information - 1",
        "Project Information -1",
        "Project Information",
    ],
    "ProjectQuants": ["ProjectQuants", "Project Information - 2"],
    "ElementQuants_L2": ["ElementQuants_L2", "Project Information - 3"],
}


def workbook_sheet_lookup(sheet_names) -> dict[str, str]:
    """Map normalized sheet title -> actual Excel sheet name."""
    lookup: dict[str, str] = {}
    for name in sheet_names:
        actual = str(name)
        decoded = _unescape_html_text(actual).strip()
        for key in {actual, decoded, actual.strip(), decoded.casefold(), actual.strip().casefold()}:
            if key and key not in lookup:
                lookup[key] = actual
    return lookup


def resolve_sheet_name(canonical_name: str, sheet_names) -> str | None:
    """
    Resolve a canonical sheet name to the actual workbook tab name.
    Uses SHEET_ALIASES when provided; otherwise requires an exact match.
    """
    lookup = workbook_sheet_lookup(sheet_names)
    candidates = SHEET_ALIASES.get(canonical_name, [canonical_name])
    for candidate in candidates:
        for key in (
            candidate,
            candidate.strip(),
            candidate.casefold(),
            candidate.strip().casefold(),
        ):
            if key in lookup:
                return lookup[key]
    return None


def all_base_sheet_names_and_aliases() -> set[str]:
    names: set[str] = set(required_base_sheets())
    for canonical, aliases in SHEET_ALIASES.items():
        names.add(canonical)
        names.update(aliases)
    return {n.strip().casefold() for n in names}


def source_sheet_name(df, fallback: str) -> str:
    """Return the Excel tab name shown to users, falling back to the canonical name."""
    if df is None:
        return fallback
    try:
        actual = df.attrs.get("source_sheet_name")
    except Exception:
        actual = None
    if actual:
        return str(actual)
    return fallback
