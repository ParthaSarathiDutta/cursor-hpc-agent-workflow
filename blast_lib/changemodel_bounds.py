"""Bounds logic mirrored from Perlmutter changemodel.json.py (±10%, sign-aware)."""

from __future__ import annotations

from decimal import Decimal

PARAMETERS = [
    "gamma",
    "lambda3",
    "c",
    "d",
    "costheta0",
    "n",
    "beta",
    "lambda2",
    "B",
    "R",
    "D",
    "lambda1",
    "A",
]

TERSEOFF_PARAM_COUNT = len(PARAMETERS)


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def make_bounds(value: Decimal) -> tuple[str, str]:
    """
    Positive: lower = 0.9 * value, upper = 1.1 * value.
    Negative: lower = 1.1 * value, upper = 0.9 * value (e.g. costheta0).
    """
    if value >= 0:
        lower = Decimal("0.9") * value
        upper = Decimal("1.1") * value
    else:
        lower = Decimal("1.1") * value
        upper = Decimal("0.9") * value
    return decimal_text(lower), decimal_text(upper)


def bounds_for_values(values: list[float]) -> dict[str, tuple[str, str]]:
    if len(values) != TERSEOFF_PARAM_COUNT:
        raise ValueError(f"Expected {TERSEOFF_PARAM_COUNT} parameters, got {len(values)}")
    out: dict[str, tuple[str, str]] = {}
    for name, val in zip(PARAMETERS, values, strict=True):
        dec = Decimal(str(val))
        out[name] = make_bounds(dec)
    return out
