"""Métricas sobre retornos simples, em frações e livres de aportes."""

from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskMetrics:
    """Resumo de uma série de retornos com frequência regular."""

    total_return: float
    cagr: float
    volatility: float | None
    sharpe: float | None
    max_drawdown: float
    var: float
    cvar: float
    observations: int


def valid_returns(returns: pd.Series) -> pd.Series:
    """Valida retornos; NaNs representam períodos não mensuráveis."""
    result = returns.dropna().astype(float)
    if result.empty or not np.isfinite(result).all() or (result < -1).any():
        raise ValueError("Retornos vazios, não finitos ou inferiores a -100%.")
    return result


def price_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Calcula retornos sem preencher lacunas ou criar cotações passadas."""
    if len(prices) < 2 or prices.empty:
        raise ValueError("São necessárias pelo menos duas observações de preços.")
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Preços devem ser positivos, finitos e sem lacunas.")
    if not prices.index.is_unique or not prices.index.is_monotonic_increasing:
        raise ValueError("Datas dos preços devem ser únicas e crescentes.")
    return prices.pct_change(fill_method=None).iloc[1:]


def drawdown(returns: pd.Series) -> pd.Series:
    """Queda da cota em relação ao pico, incluindo a cota inicial igual a 1."""
    wealth = (1 + valid_returns(returns)).cumprod()
    peak = wealth.cummax().clip(lower=1.0)
    return (wealth / peak - 1).rename("Drawdown")


def risk_metrics(
    returns: pd.Series,
    risk_free: float | pd.Series = 0.0,
    periods_per_year: int = 12,
    confidence: float = 0.95,
) -> RiskMetrics:
    """Calcula CAGR, volatilidade, Sharpe e perdas históricas VaR/CVaR.

    Args:
        returns: Retornos por período em fração (0.01 = 1%).
        risk_free: Taxa anual efetiva escalar ou série por período alinhada.
        periods_per_year: 12 para mensal; 252 para diário.
        confidence: Confiança do quantil histórico, estritamente entre 0 e 1.

    Returns:
        Métricas; Sharpe/volatilidade indefinidos são None. VaR e CVaR
        representam perdas não negativas por período, sem anualização.
    """
    if periods_per_year <= 0 or not 0 < confidence < 1:
        raise ValueError("Frequência ou confiança inválida.")
    r = valid_returns(returns)
    if isinstance(risk_free, pd.Series):
        rf = risk_free.reindex(r.index).astype(float)
        if not np.isfinite(rf).all() or (rf < -1).any():
            raise ValueError("Taxa de referência incompleta ou inválida na janela.")
    else:
        if not np.isfinite(risk_free) or risk_free <= -1:
            raise ValueError("Taxa anual deve ser finita e maior que -100%.")
        rf = pd.Series((1 + risk_free) ** (1 / periods_per_year) - 1, index=r.index)
    excess = r - rf
    sigma = float(r.std(ddof=1)) if len(r) > 1 else None
    excess_sigma = float(excess.std(ddof=1)) if len(r) > 1 else 0.0
    factor = float(cast(float, (1 + r).prod()))
    cutoff = float(cast(float, r.quantile(1 - confidence)))
    return RiskMetrics(
        total_return=factor - 1,
        cagr=factor ** (periods_per_year / len(r)) - 1,
        volatility=sigma * np.sqrt(periods_per_year) if sigma is not None else None,
        sharpe=(float(excess.mean()) / excess_sigma * np.sqrt(periods_per_year))
        if excess_sigma > 1e-12
        else None,
        max_drawdown=float(drawdown(r).min()),
        var=max(0.0, -cutoff),
        cvar=max(0.0, -float(r[r <= cutoff].mean())),
        observations=len(r),
    )
