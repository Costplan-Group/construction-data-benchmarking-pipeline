"""Allowed values and checks for Project Information attributes stored on DimProject."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ingestion_engine.coercion import clean_value

SPEC_LEVELS: tuple[str, ...] = ("Low", "Medium", "High")
SITE_TYPES: tuple[str, ...] = ("Greenfield", "Brownfield")
COMPLEXITY_RANGE: tuple[int, int] = (1, 5)

CHOICE_FIELDS: dict[str, tuple[str, ...]] = {
    "SpecLevel": SPEC_LEVELS,
    "SiteType": SITE_TYPES,
}
NON_NEGATIVE_INT_FIELDS: tuple[str, ...] = ("NrOfStoreys",)
NON_NEGATIVE_DECIMAL_FIELDS: tuple[str, ...] = (
    "TotalHeightGroundToRoof",
    "BasementArea",
    "BasementHeight",
)


def is_blank(value) -> bool:
    """True for None, NaN/NaT and empty or whitespace-only strings. 0 and False are not blank."""
    return clean_value(value) is None


def canonical_choice(value, allowed: tuple[str, ...]) -> str | None:
    """Case/whitespace-insensitive match against ``allowed``; None when nothing matches."""
    text = str(value).strip().casefold()
    for option in allowed:
        if option.casefold() == text:
            return option
    return None


def parse_decimal(value) -> Decimal | None:
    """Decimal for numeric input (bools excluded), else None. Call only on non-blank values."""
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(clean_value(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def parse_whole_number(value) -> int | None:
    """int for whole-number input (3, 3.0, "3"), else None. Call only on non-blank values."""
    number = parse_decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def complexity_rating_error(value) -> str | None:
    number = parse_whole_number(value)
    low, high = COMPLEXITY_RANGE
    if number is None or not low <= number <= high:
        return f"Invalid ComplexityRating '{value}'. Allowed: whole number {low}-{high}"
    return None


def choice_error(field: str, value) -> str | None:
    allowed = CHOICE_FIELDS[field]
    if canonical_choice(value, allowed) is None:
        return f"Invalid {field} '{value}'. Allowed: {', '.join(allowed)}"
    return None


def non_negative_int_error(field: str, value) -> str | None:
    number = parse_whole_number(value)
    if number is None or number < 0:
        return f"Invalid {field} '{value}'. Expected a non-negative whole number"
    return None


def non_negative_decimal_error(field: str, value) -> str | None:
    number = parse_decimal(value)
    if number is None or number < 0:
        return f"Invalid {field} '{value}'. Expected a non-negative number"
    return None


VALIDATED_FIELDS: tuple[str, ...] = (
    *CHOICE_FIELDS,
    "ComplexityRating",
    *NON_NEGATIVE_INT_FIELDS,
    *NON_NEGATIVE_DECIMAL_FIELDS,
)


def attribute_error(field: str, value) -> tuple[str, str] | None:
    """(error_type, message) when a value is invalid; None when valid or blank."""
    if is_blank(value):
        return None
    if field in CHOICE_FIELDS:
        message, error_type = choice_error(field, value), "DOMAIN"
    elif field == "ComplexityRating":
        message, error_type = complexity_rating_error(value), "DOMAIN"
    elif field in NON_NEGATIVE_INT_FIELDS:
        message, error_type = non_negative_int_error(field, value), "INVALID_NUMBER"
    elif field in NON_NEGATIVE_DECIMAL_FIELDS:
        message, error_type = non_negative_decimal_error(field, value), "INVALID_NUMBER"
    else:
        raise KeyError(f"{field} is not a validated project attribute")
    return (error_type, message) if message else None
