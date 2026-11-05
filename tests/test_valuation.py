"""Valuation em casos conhecidos e condições de validade econômica."""

import pytest

from core.valuation import dividend_valuation, monthly_income


def test_dividend_models() -> None:
    dyt, gordon = dividend_valuation(2, 0.08, 0.03, 0.10)
    assert dyt == 25
    assert gordon == pytest.approx(2.06 / 0.07)


def test_gordon_rejects_growth_at_or_above_discount() -> None:
    with pytest.raises(ValueError):
        dividend_valuation(2, 0.08, 0.10, 0.10)


def test_income_uses_editable_withholding() -> None:
    assert monthly_income(100_000, 5, 0.06, 0.30) == pytest.approx(70)
