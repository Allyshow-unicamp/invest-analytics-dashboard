"""Valuation e renda parametrizados: premissas explícitas, sem cotações fixas."""

import math


def dividend_valuation(
    annual_dividend: float, required_yield: float, growth: float, discount: float
) -> tuple[float, float]:
    """Retorna preço por yield e Gordon D1/(k-g), exigindo k > g."""
    if not all(math.isfinite(v) for v in (annual_dividend, required_yield, growth, discount)):
        raise ValueError("Premissas devem ser finitas.")
    if annual_dividend < 0 or required_yield <= 0 or growth <= -1 or discount <= growth:
        raise ValueError("Exija DPA >= 0, yield > 0, g > -100% e desconto > crescimento.")
    return annual_dividend / required_yield, annual_dividend * (1 + growth) / (discount - growth)


def monthly_income(capital_brl: float, fx: float, annual_yield: float, withholding: float) -> float:
    """Renda mensal estimada em USD; retenção é uma hipótese do usuário."""
    if not all(math.isfinite(v) for v in (capital_brl, fx, annual_yield, withholding)):
        raise ValueError("Premissas devem ser finitas.")
    if capital_brl < 0 or fx <= 0 or annual_yield < 0 or not 0 <= withholding <= 1:
        raise ValueError("Premissas de renda inválidas.")
    return capital_brl / fx * annual_yield / 12 * (1 - withholding)
