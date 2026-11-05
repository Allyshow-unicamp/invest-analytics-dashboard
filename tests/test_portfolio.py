"""Regressões de fluxos, dividendos, perda inicial e ausência de lookahead."""

import numpy as np
import pandas as pd
import pytest

from core.bazin import radar, weighted_dpa
from core.portfolio import backtest, benchmark_backtest, bootstrap, simulate_portfolios
from data.models import MarketData
from services.analytics import analyze


def test_dca_and_benchmark_share_identical_end_month_flows(dates: pd.DatetimeIndex) -> None:
    prices = pd.DataFrame({"A": [100.0, 110.0, 99.0]}, index=dates)
    divs = pd.DataFrame(0.0, index=dates, columns=["A"])
    cash = pd.Series(0.0, index=dates)
    actual = backtest(prices, divs, cash, capital=100, contribution=10)
    reference = benchmark_backtest(pd.Series([np.nan, 0.1, -0.1], index=dates), capital=100, contribution=10)
    assert actual["wealth"].tolist() == pytest.approx([100, 120, 118])
    assert actual["wealth"].tolist() == pytest.approx(reference["wealth"].tolist())
    assert actual["contributed"].tolist() == [100, 110, 120]
    assert actual["return"].iloc[1:].tolist() == pytest.approx([0.1, -0.1])


def test_dividends_are_not_credited_on_new_month_end_contributions(dates: pd.DatetimeIndex) -> None:
    prices = pd.DataFrame({"A": [100.0] * 3}, index=dates)
    divs = pd.DataFrame({"A": [0.0, 10.0, 10.0]}, index=dates)
    result = backtest(prices, divs, pd.Series(0.0, index=dates), capital=100, contribution=100)
    assert result["wealth"].tolist() == pytest.approx([100, 210, 331])
    assert result["dividends"].tolist() == pytest.approx([0, 10, 31])


def test_no_drip_keeps_dividends_in_reserve(dates: pd.DatetimeIndex) -> None:
    prices = pd.DataFrame({"A": [100.0] * 3}, index=dates)
    divs = pd.DataFrame({"A": [0.0, 10.0, 10.0]}, index=dates)
    result = backtest(prices, divs, pd.Series(0.0, index=dates), capital=100, contribution=0, reinvest=False)
    assert result["wealth"].tolist() == pytest.approx([100, 110, 120])
    assert result["cash"].tolist() == pytest.approx([0, 10, 20])


def test_zero_initial_capital_does_not_generate_artificial_return(dates: pd.DatetimeIndex) -> None:
    prices = pd.DataFrame({"A": [100.0] * 3}, index=dates)
    result = backtest(prices, prices * 0, pd.Series(0.0, index=dates), capital=0, contribution=10)
    assert result["wealth"].tolist() == [0, 10, 20]
    assert result["return"].iloc[:2].isna().all()
    assert result["return"].iloc[2] == 0


def test_bazin_uses_only_five_complete_prior_calendar_years() -> None:
    index = pd.date_range("2015-01-31", "2020-12-31", freq="ME")
    divs = pd.Series([float(d.year - 2014) / 12 for d in index], index=index)
    as_of = pd.Timestamp("2020-12-31")
    assert weighted_dpa(divs, as_of) == pytest.approx(55 / 15)
    divs.loc["2020"] = 1_000_000
    assert weighted_dpa(divs, as_of) == pytest.approx(55 / 15)
    assert weighted_dpa(divs.iloc[1:], as_of) is None


def test_zero_dividend_year_is_not_missing_history() -> None:
    index = pd.date_range("2015-01-31", "2019-12-31", freq="ME")
    dividends = pd.DataFrame(0.0, index=index, columns=["A"])
    output = radar(pd.Series({"A": 10.0}), dividends, pd.Timestamp("2020-01-31"))
    assert output.loc["A", "signal"] == "SEM DIVIDENDOS"
    assert output.loc["A", "allocation"] == 0


def test_service_keeps_warmup_history_and_equal_contributions(market_data: MarketData) -> None:
    result = analyze(market_data, "2016-01-01", 100_000, 1_000)
    assert result.radar is not None
    assert not result.radar["signal"].eq("SEM HISTÓRICO").any()
    assert result.summary["contributed"].nunique() == 1
    assert result.summary["contributed"].iloc[0] == 219_000
    for frame in result.strategies.values():
        assert frame["contributed"].iloc[0] == 100_000


def test_bootstrap_is_reproducible_and_includes_time_zero() -> None:
    returns = pd.Series([0.01] * 12)
    paths = bootstrap(returns, 100, 10, months=2, simulations=3)
    np.testing.assert_allclose(paths, [[100, 111, 122.11]] * 3)
    np.testing.assert_array_equal(paths, bootstrap(returns, 100, 10, months=2, simulations=3))


def test_cloud_weights_are_long_only_and_sum_to_one() -> None:
    returns = pd.DataFrame({"A": [0.01, -0.02, 0.03], "B": [0.02, 0.01, 0.01]})
    cloud = simulate_portfolios(returns, samples=100)
    np.testing.assert_allclose(cloud[["A", "B"]].sum(axis=1), 1)
    assert (cloud[["A", "B"]] >= 0).all().all()


def test_missing_cash_cannot_be_treated_as_zero(dates: pd.DatetimeIndex) -> None:
    prices = pd.DataFrame({"A": [100.0] * 3}, index=dates)
    with pytest.raises(ValueError, match="caixa"):
        backtest(prices, prices * 0, pd.Series(dtype=float))
