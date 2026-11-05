"""Orçamento em centavos, metas, lotes, ausência de vendas e otimização de risco."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from core.allocation import AllocationStrategy, Position, RebalancingEngine, normalize_b3_ticker


@pytest.fixture
def two_assets() -> tuple[Position, Position]:
    return (Position("ITUB4", 0, 0, 0.5), Position("BOVA11", 0, 0, 0.5, "ETF"))


@pytest.fixture
def history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ITUB4.SA": np.tile([-0.01, 0.01, -0.01, 0.01], 30) + 0.001,
            "BOVA11.SA": np.tile([-0.02, -0.02, 0.02, 0.02], 30) + 0.0005,
        },
        index=pd.bdate_range("2024-01-01", periods=120),
    )


def test_insufficient_contribution_stays_in_cash(two_assets: tuple[Position, Position]) -> None:
    result = RebalancingEngine(two_assets, {"ITUB4": 100, "BOVA11": 120}).allocate(50)
    assert result.orders["buy_quantity"].sum() == 0
    assert result.allocated == 0
    assert result.residual_cash == 50
    assert result.final_value == 50


def test_balanced_portfolio_receives_proportional_new_money() -> None:
    positions = [Position("ITUB4", 50, 1, 0.5), Position("BOVA11", 50, 1, 0.5)]
    result = RebalancingEngine(positions, {"ITUB4": 1, "BOVA11": 1}).allocate(20)
    assert result.orders["buy_quantity"].tolist() == [10, 10]
    assert result.orders["final_weight"].tolist() == pytest.approx([0.5, 0.5])
    assert result.residual_cash == 0


def test_rebalance_prioritizes_underweight_without_selling() -> None:
    positions = [Position("ITUB4", 90, 1, 0.5), Position("BOVA11", 10, 1, 0.5)]
    engine = RebalancingEngine(positions, {"ITUB4": 1, "BOVA11": 1})
    result = engine.allocate(20)
    proportional = engine.allocate(20, AllocationStrategy.PROPORTIONAL)
    assert result.orders["buy_quantity"].tolist() == [0, 20]
    assert proportional.orders["buy_quantity"].tolist() == [10, 10]
    assert (result.orders["final_quantity"] >= result.orders["current_quantity"]).all()


@pytest.mark.parametrize("strategy", list(AllocationStrategy))
def test_zero_target_blocks_new_orders_even_with_existing_holdings(
    strategy: AllocationStrategy, history: pd.DataFrame
) -> None:
    positions = [Position("ITUB4", 50, 1, 0), Position("BOVA11", 0, 0, 1)]
    result = RebalancingEngine(positions, {"ITUB4": 1, "BOVA11": 1}, history).allocate(100, strategy)
    assert result.orders.loc["ITUB4.SA", "buy_quantity"] == 0
    assert result.orders.loc["ITUB4.SA", "final_quantity"] == 50
    assert result.orders.loc["BOVA11.SA", "buy_quantity"] == 100


def test_custom_lot_size_and_exact_money() -> None:
    result = RebalancingEngine([Position("ITUB4", 0, 0, 1, lot_size=100)], {"ITUB4": 10}).allocate(2500)
    assert result.orders.iloc[0]["buy_quantity"] == 200
    assert result.allocated == 2000
    assert result.residual_cash == 500
    cents = RebalancingEngine([Position("ITUB4", 0, 0, 1)], {"ITUB4": 19.999999}).allocate(999.99)
    assert cents.allocated == 980
    assert cents.residual_cash == 19.99


def test_zero_contribution_preserves_positions() -> None:
    result = RebalancingEngine([Position("ITUB4", 10, 12, 1)], {"ITUB4": 20}).allocate(0)
    assert result.current_value == result.final_value == 200
    assert result.orders.iloc[0]["buy_quantity"] == 0


def test_average_price_does_not_change_market_weight() -> None:
    first = Position("ITUB4", 10, 20, 1)
    a = RebalancingEngine([first], {"ITUB4": 50}).allocate(100)
    b = RebalancingEngine([replace(first, average_price=1000)], {"ITUB4": 50}).allocate(100)
    assert a.orders["buy_quantity"].tolist() == b.orders["buy_quantity"].tolist()
    assert a.orders.iloc[0]["average_price_after"] == pytest.approx(25)


def test_minimum_variance_matches_two_uncorrelated_assets(
    two_assets: tuple[Position, Position], history: pd.DataFrame
) -> None:
    result = RebalancingEngine(two_assets, {"ITUB4": 1, "BOVA11": 1}, history).allocate(
        10_000, AllocationStrategy.MIN_VARIANCE
    )
    assert result.orders["final_weight"].tolist() == pytest.approx([0.8, 0.2], abs=0.0002)
    expected = np.sqrt(np.array([0.8, 0.2]) @ (history.cov().to_numpy() * 252) @ np.array([0.8, 0.2]))
    assert result.volatility_after == pytest.approx(expected, rel=0.001)


def test_optimization_accounts_for_existing_positions(history: pd.DataFrame) -> None:
    positions = [Position("ITUB4", 0, 0, 0.5), Position("BOVA11", 1000, 1, 0.5)]
    result = RebalancingEngine(positions, {"ITUB4": 1, "BOVA11": 1}, history).allocate(
        100, AllocationStrategy.MIN_VARIANCE
    )
    assert result.orders["buy_quantity"].tolist() == [100, 0]
    assert result.orders.loc["BOVA11.SA", "final_quantity"] == 1000


def test_max_sharpe_improves_over_direct_proportional(
    two_assets: tuple[Position, Position], history: pd.DataFrame
) -> None:
    engine = RebalancingEngine(two_assets, {"ITUB4": 1, "BOVA11": 1}, history)
    result = engine.allocate(9000, AllocationStrategy.MAX_SHARPE)
    weights = result.orders["final_weight"].to_numpy()
    mean, cov = history.mean().to_numpy() * 252, history.cov().to_numpy() * 252
    achieved = weights @ mean / np.sqrt(weights @ cov @ weights)
    reference = np.array([0.5, 0.5])
    assert achieved > reference @ mean / np.sqrt(reference @ cov @ reference)
    assert weights == pytest.approx([8 / 9, 1 / 9], abs=0.001)


def test_cash_is_included_in_final_weights_and_risk(history: pd.DataFrame) -> None:
    positions = [Position("ITUB4", 1, 1, 1), Position("BOVA11", 0, 0, 0)]
    result = RebalancingEngine(positions, {"ITUB4": 100, "BOVA11": 100}, history).allocate(50)
    assert result.residual_cash == 50
    assert result.orders["final_weight"].sum() == pytest.approx(2 / 3)
    assert result.volatility_after == pytest.approx(result.volatility_before * 2 / 3)
    assert result.volatility_after_invested == pytest.approx(result.volatility_before)


@pytest.mark.parametrize("strategy", [AllocationStrategy.MIN_VARIANCE, AllocationStrategy.MAX_SHARPE])
def test_risk_optimization_rejects_short_history(strategy: AllocationStrategy, history: pd.DataFrame) -> None:
    positions = [Position("ITUB4", 0, 0, 0.5), Position("BOVA11", 0, 0, 0.5)]
    engine = RebalancingEngine(positions, {"ITUB4": 10, "BOVA11": 10}, history.iloc[:20])
    with pytest.raises(ValueError, match="60 retornos"):
        engine.allocate(100, strategy)
    assert engine.allocate(100).volatility_after is None


@pytest.mark.parametrize(
    "ticker, expected",
    [(" itub4 ", "ITUB4.SA"), ("ITUB4F", "ITUB4.SA"), ("hglg11.sa", "HGLG11.SA"), ("B5P211", "B5P211.SA")],
)
def test_b3_ticker_normalization(ticker: str, expected: str) -> None:
    assert normalize_b3_ticker(ticker) == expected


@pytest.mark.parametrize("ticker", ["AAPL", "^BVSP", "ITUB4.L", "", "../../PETR4"])
def test_non_b3_symbols_are_rejected(ticker: str) -> None:
    with pytest.raises(ValueError):
        normalize_b3_ticker(ticker)


@pytest.mark.parametrize(
    "position",
    [
        Position("ITUB4", -1, 0, 1),
        Position("ITUB4", 0.5, 0, 1),
        Position("ITUB4", 1, np.nan, 1),
        Position("ITUB4", 1, 0, 0),
        Position("ITUB4", 1, 0, 1, lot_size=0),
    ],
)
def test_invalid_positions_are_rejected(position: Position) -> None:
    with pytest.raises(ValueError):
        RebalancingEngine([position], {"ITUB4": 1})


def test_duplicate_tickers_after_normalization() -> None:
    with pytest.raises(ValueError, match="duplicados"):
        RebalancingEngine([Position("ITUB4", 0, 0, 0.5), Position("ITUB4.SA", 0, 0, 0.5)], {"ITUB4": 1})


def test_random_budgets_never_overspend_or_sell() -> None:
    rng = np.random.default_rng(17)
    for _ in range(100):
        targets = rng.dirichlet([1, 1, 1])
        positions = [
            Position(t, int(rng.integers(0, 200)), 20, float(w))
            for t, w in zip(["ITUB4", "HGLG11", "BOVA11"], targets, strict=True)
        ]
        prices = dict(zip(["ITUB4", "HGLG11", "BOVA11"], rng.uniform(1, 200, 3), strict=True))
        contribution = round(float(rng.uniform(0, 10000)), 2)
        for strategy in [AllocationStrategy.REBALANCE, AllocationStrategy.PROPORTIONAL]:
            result = RebalancingEngine(positions, prices).allocate(contribution, strategy)
            assert result.allocated + result.residual_cash == pytest.approx(contribution)
            assert 0 <= result.allocated <= contribution
            assert (result.orders["buy_quantity"] >= 0).all()
            assert (result.orders["final_quantity"] >= result.orders["current_quantity"]).all()
            assert result.orders[
                "final_weight"
            ].sum() + result.residual_cash / result.final_value == pytest.approx(1)
