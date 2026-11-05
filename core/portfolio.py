"""Carteiras sem alavancagem, fluxos consistentes e bootstrap reproduzível."""

from collections.abc import Mapping
from typing import cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from core.bazin import radar
from core.metrics import price_returns, valid_returns


def normalize_weights(columns: pd.Index, weights: Mapping[str, float] | None) -> pd.Series:
    """Exige pesos para todos os ativos e normaliza uma soma positiva."""
    if weights is not None and set(weights) != set(columns):
        raise ValueError("Os pesos devem corresponder exatamente aos ativos.")
    result = (
        pd.Series(weights, dtype=float).reindex(columns)
        if weights is not None
        else pd.Series(1.0, index=columns)
    )
    if not np.isfinite(result).all() or (result < 0).any() or result.sum() <= 0:
        raise ValueError("Pesos inválidos: use valores não negativos com soma positiva.")
    return result / result.sum()


def validate_cash(capital: float, contribution: float) -> None:
    """Valida capital e aportes sem permitir dívida ou um estudo vazio."""
    if not np.isfinite([capital, contribution]).all() or min(capital, contribution) < 0:
        raise ValueError("Capital e aporte devem ser finitos e não negativos.")
    if capital + contribution <= 0:
        raise ValueError("Informe capital inicial ou aporte maior que zero.")


def backtest(
    prices: pd.DataFrame,
    dividends: pd.DataFrame,
    cash_returns: pd.Series,
    *,
    capital: float = 100_000,
    contribution: float = 1_000,
    weights: Mapping[str, float] | None = None,
    use_bazin: bool = False,
    buy_yield: float = 0.085,
    hold_yield: float = 0.06,
    reinvest: bool = True,
) -> pd.DataFrame:
    """Simula posições mensais com aportes no fim de cada intervalo.

    A primeira linha é uma posição inicial: nenhum retorno ou aporte mensal.
    Cada mês seguinte marca posições, remunera caixa anterior, credita proventos,
    mede TWR antes do aporte e investe recursos no fechamento. Dividendos
    completos são mantidos separadamente para o aquecimento do sinal Bazin.
    Sem DRIP, dividendos ficam numa reserva remunerada e não são realocados.
    """
    validate_cash(capital, contribution)
    price_returns(prices)
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("Preços precisam de DatetimeIndex mensal.")
    if not prices.index.to_period("M").equals(pd.period_range(prices.index[0], prices.index[-1], freq="M")):
        raise ValueError("O backtest exige meses consecutivos, sem duplicatas.")
    base = normalize_weights(prices.columns, weights)
    monthly_dividends = dividends.reindex(index=prices.index, columns=prices.columns)
    cdi = cash_returns.reindex(prices.index[1:])
    if not np.isfinite(monthly_dividends.to_numpy()).all() or (monthly_dividends < 0).any().any():
        raise ValueError("Proventos ausentes ou inválidos no período.")
    if not np.isfinite(cdi).all() or (cdi < -1).any():
        raise ValueError("Retornos de caixa ausentes ou inválidos.")
    shares = pd.Series(0.0, index=prices.columns)
    cash, reserve, contributed, cumulative_dividends = capital, 0.0, capital, 0.0
    previous = capital
    rows: list[dict[str, object]] = []
    for i, timestamp in enumerate(prices.index):
        quotes = cast(pd.Series, prices.loc[timestamp])
        received, r = 0.0, float("nan")
        if i:
            cash *= 1 + float(cast(float, cdi.at[timestamp]))
            reserve *= 1 + float(cast(float, cdi.at[timestamp]))
            received = float((shares * cast(pd.Series, monthly_dividends.loc[timestamp])).sum())
            cumulative_dividends += received
            if reinvest:
                cash += received
            else:
                reserve += received
            before_flow = float((shares * quotes).sum()) + cash + reserve
            r = before_flow / previous - 1 if previous > 0 else float("nan")
            cash += contribution
            contributed += contribution
        allocation = base
        if use_bazin:
            allocation = radar(
                quotes,
                dividends,
                timestamp,
                buy_yield,
                hold_yield,
                {str(key): float(value) for key, value in base.items()},
            )["allocation"]
        if allocation.sum() > 0:
            shares += cash * allocation / quotes
            cash = 0.0
        wealth = float((shares * quotes).sum()) + cash + reserve
        rows.append(
            {
                "date": timestamp,
                "wealth": wealth,
                "contributed": contributed,
                "cash": cash + reserve,
                "dividends": cumulative_dividends,
                "monthly_dividends": received,
                "return": r,
            }
        )
        previous = wealth
    return pd.DataFrame(rows).set_index("date")


def benchmark_backtest(returns: pd.Series, *, capital: float, contribution: float) -> pd.DataFrame:
    """Benchmark com uma linha-base NaN e os mesmos aportes de fim de mês."""
    validate_cash(capital, contribution)
    if len(returns) < 2 or not pd.isna(returns.iloc[0]):
        raise ValueError("Benchmark exige uma linha inicial NaN e ao menos um retorno.")
    valid_returns(returns.iloc[1:])
    if returns.iloc[1:].isna().any():
        raise ValueError("Benchmark contém lacunas.")
    wealth, contributed = capital, capital
    rows = [{"wealth": wealth, "contributed": contributed, "return": float("nan")}]
    for r in returns.iloc[1:]:
        measured = float(r) if wealth > 0 else float("nan")
        wealth = wealth * (1 + r) + contribution
        contributed += contribution
        rows.append({"wealth": wealth, "contributed": contributed, "return": measured})
    return pd.DataFrame(rows, index=returns.index)


def simulate_portfolios(
    returns: pd.DataFrame, annual_risk_free: float = 0.0, samples: int = 3000, seed: int = 42
) -> pd.DataFrame:
    """Nuvem Monte Carlo long-only; não é uma fronteira eficiente otimizada.

    Retorno esperado é a média aritmética anualizada, distinta do CAGR.
    """
    if len(returns) < 2 or returns.empty or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Retornos insuficientes ou inválidos para a simulação.")
    if (returns < -1).any().any() or samples < 1 or not np.isfinite(annual_risk_free):
        raise ValueError("Parâmetros de simulação inválidos.")
    rng = np.random.default_rng(seed)
    weights = rng.dirichlet(np.ones(returns.shape[1]), size=samples)
    # Inclui carteiras unitárias e pesos iguais para facilitar comparação.
    weights = np.vstack([weights, np.eye(returns.shape[1]), np.ones(returns.shape[1]) / returns.shape[1]])
    expected = weights @ (returns.mean().to_numpy() * 12)
    covariance = returns.cov().to_numpy() * 12
    volatility = np.sqrt(np.maximum(0, np.einsum("ij,jk,ik->i", weights, covariance, weights)))
    scores = np.divide(
        expected - annual_risk_free, volatility, out=np.full(len(weights), np.nan), where=volatility > 1e-12
    )
    result = pd.DataFrame(weights, columns=returns.columns)
    result["expected_return"], result["volatility"], result["score"] = expected, volatility, scores
    return result


def bootstrap(
    returns: pd.Series,
    capital: float,
    contribution: float,
    months: int = 120,
    simulations: int = 500,
    seed: int = 42,
) -> NDArray[np.float64]:
    """Sorteia meses iid com reposição; inclui o capital no instante zero."""
    validate_cash(capital, contribution)
    r = valid_returns(returns)
    if len(r) < 12 or months < 1 or simulations < 1:
        raise ValueError("Bootstrap exige 12 retornos e horizonte/simulações positivos.")
    rng = np.random.default_rng(seed)
    draws = rng.choice(r.to_numpy(), size=(simulations, months))
    paths = np.full((simulations, months + 1), capital, dtype=float)
    for month in range(months):
        paths[:, month + 1] = paths[:, month] * (1 + draws[:, month]) + contribution
    return paths
