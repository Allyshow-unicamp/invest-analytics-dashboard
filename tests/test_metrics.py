"""Exemplos calculáveis manualmente para as métricas financeiras."""

import numpy as np
import pandas as pd
import pytest

from core.metrics import drawdown, price_returns, risk_metrics


def test_first_loss_is_measured_against_initial_capital() -> None:
    r = pd.Series([-0.20, 0.10, -0.50])
    assert drawdown(r).tolist() == pytest.approx([-0.20, -0.12, -0.56])
    assert risk_metrics(r).max_drawdown == pytest.approx(-0.56)


def test_compounding_and_geometric_annualization() -> None:
    m = risk_metrics(pd.Series([0.10, -0.10]), periods_per_year=2)
    assert m.total_return == pytest.approx(-0.01)
    assert m.cagr == pytest.approx(-0.01)


def test_sharpe_uses_periodic_excess_returns() -> None:
    r = pd.Series([0.03, -0.01, 0.02, 0.01])
    rf = pd.Series([0.01, 0.005, 0.002, 0.003])
    excess = r - rf
    assert risk_metrics(r, rf).sharpe == pytest.approx(excess.mean() / excess.std(ddof=1) * np.sqrt(12))


def test_zero_volatility_is_undefined_sharpe() -> None:
    m = risk_metrics(pd.Series([0.01] * 12))
    assert m.sharpe is None
    assert m.volatility == pytest.approx(0)
    assert m.var == 0


def test_historical_tail_and_total_loss() -> None:
    m = risk_metrics(pd.Series([-0.20, -0.10, 0.0, 0.10]), confidence=0.75)
    assert m.var == pytest.approx(0.125)
    assert m.cvar == pytest.approx(0.20)
    assert risk_metrics(pd.Series([-1.0, 0.10])).cagr == -1


@pytest.mark.parametrize("values", [[], [np.inf], [-1.01]])
def test_invalid_returns_are_rejected(values: list[float]) -> None:
    with pytest.raises(ValueError):
        risk_metrics(pd.Series(values, dtype=float))


def test_missing_reference_cannot_be_filled_with_zero() -> None:
    with pytest.raises(ValueError, match="incompleta"):
        risk_metrics(pd.Series([0.01, 0.02]), pd.Series([0.01]))


def test_prices_do_not_forward_fill() -> None:
    with pytest.raises(ValueError, match="lacunas"):
        price_returns(pd.DataFrame({"A": [10, np.nan, 12]}))
