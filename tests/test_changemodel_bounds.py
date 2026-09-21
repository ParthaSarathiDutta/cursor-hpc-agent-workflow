"""Tests for changemodel.json.py bound logic (sign-aware ±10%)."""

from decimal import Decimal

from blast_lib.changemodel_bounds import make_bounds


def test_positive_bounds():
    lo, hi = make_bounds(Decimal("100"))
    assert float(lo) == 90.0
    assert float(hi) == 110.0


def test_negative_costheta_bounds():
    lo, hi = make_bounds(Decimal("-0.05"))
    assert Decimal(lo) < Decimal("-0.05")
    assert Decimal(hi) > Decimal("-0.05")
    assert Decimal(lo) == Decimal("1.1") * Decimal("-0.05")
    assert Decimal(hi) == Decimal("0.9") * Decimal("-0.05")
