"""Decimal precision helpers for staging inserts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def decimal_fits_precision_scale(value: Decimal, precision: int, scale: int) -> bool:
    sign, digits, exponent = value.as_tuple()
    frac_digits = -exponent if exponent < 0 else 0
    int_digits = len(digits) - frac_digits
    if int_digits < 0:
        int_digits = 0
    return frac_digits <= scale and int_digits <= (precision - scale)


def coerce_decimal_to_precision_scale(
    value: Decimal | None, precision: int, scale: int
) -> Decimal | None:
    if value is None:
        return None
    quant = Decimal("1").scaleb(-scale)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    if decimal_fits_precision_scale(rounded, precision, scale):
        return rounded
    return None
