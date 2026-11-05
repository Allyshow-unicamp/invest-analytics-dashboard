"""Orquestra comparações na mesma janela e na mesma moeda."""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from core.bazin import B3_WEIGHTS, radar
from core.metrics import price_returns, risk_metrics
from core.portfolio import backtest, benchmark_backtest
from data.models import DataError, MarketData


@dataclass(frozen=True)
class Analysis:
    """Resultado pronto para apresentação, sem dependência de UI."""

    strategies: dict[str, pd.DataFrame]
    summary: pd.DataFrame
    asset_returns: pd.DataFrame
    radar: pd.DataFrame | None


def analyze(
    data: MarketData,
    start: str,
    capital: float,
    contribution: float,
    market: str = "B3",
    buy_yield: float = 0.085,
    hold_yield: float = 0.06,
    reinvest: bool = True,
    annual_risk_free: float = 0.0,
    legacy_weights: bool = True,
) -> Analysis:
    """Executa Bazin/DCA/benchmark/caixa preservando histórico de aquecimento."""
    prices = data.prices.loc[start:]
    if len(prices) < 3:
        raise DataError("Selecione ao menos três fechamentos para a análise.")
    dividend_window = data.dividends.reindex(index=prices.index, columns=prices.columns)
    if not np.isfinite(dividend_window.to_numpy()).all():
        raise DataError("Proventos incompletos no período de simulação.")
    cash = data.cash_returns.reindex(prices.index)
    weights = (
        {str(t): B3_WEIGHTS.get(str(t), 1.0) for t in prices.columns}
        if market == "B3" and legacy_weights
        else None
    )
    strategies = {
        "DCA": backtest(
            prices,
            data.dividends,
            cash,
            capital=capital,
            contribution=contribution,
            weights=weights,
            reinvest=reinvest,
        )
    }
    latest_radar = None
    if market == "B3":
        strategies = {
            "Radar Bazin": backtest(
                prices,
                data.dividends,
                cash,
                use_bazin=True,
                buy_yield=buy_yield,
                hold_yield=hold_yield,
                capital=capital,
                contribution=contribution,
                weights=weights,
                reinvest=reinvest,
            ),
            **strategies,
        }
        latest_radar = radar(
            prices.iloc[-1], data.dividends, prices.index[-1], buy_yield, hold_yield, weights
        )
    index_returns = price_returns(data.benchmark.reindex(prices.index).to_frame()).iloc[:, 0]
    index_returns = index_returns.reindex(prices.index)
    cash.iloc[0] = float("nan")
    strategies[data.benchmark_name] = benchmark_backtest(
        index_returns, capital=capital, contribution=contribution
    )
    cash_name = "CDI" if market == "B3" else "Caixa USD (0%)"
    strategies[cash_name] = benchmark_backtest(cash, capital=capital, contribution=contribution)
    rf: float | pd.Series = data.cash_returns if market == "B3" else annual_risk_free
    rows = []
    for name, frame in strategies.items():
        r = frame["return"].dropna()
        metrics = asdict(risk_metrics(r, rf)) if not r.empty else {}
        rows.append(
            {
                "strategy": name,
                "wealth": float(frame["wealth"].iloc[-1]),
                "contributed": float(frame["contributed"].iloc[-1]),
                **metrics,
            }
        )
    asset_returns = price_returns(data.adjusted_prices.reindex(prices.index))
    return Analysis(strategies, pd.DataFrame(rows).set_index("strategy"), asset_returns, latest_radar)
