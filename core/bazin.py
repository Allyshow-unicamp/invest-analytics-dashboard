"""Regra Bazin do legado: cinco anos completos, pesos 1 a 5."""

from collections.abc import Mapping

import numpy as np
import pandas as pd

B3_WEIGHTS: dict[str, float] = {
    "ITUB4.SA": 0.12,
    "BBAS3.SA": 0.12,
    "ITSA4.SA": 0.10,
    "BBSE3.SA": 0.12,
    "PETR4.SA": 0.05,
    "VALE3.SA": 0.05,
    "EQTL3.SA": 0.10,
    "TAEE11.SA": 0.12,
    "SBSP3.SA": 0.06,
    "WEGE3.SA": 0.10,
    "ABEV3.SA": 0.02,
    "RADL3.SA": 0.02,
    "LREN3.SA": 0.02,
}


def weighted_dpa(dividends: pd.Series, as_of: pd.Timestamp, years: int = 5) -> float | None:
    """Usa somente anos anteriores completos; zero difere de dado ausente.

    Os valores por ação devem ter a mesma base de desdobramentos dos preços.
    Um mês NaN ou ausente impede o sinal, inclusive antes de uma listagem.
    """
    if years < 1:
        raise ValueError("A janela deve conter ao menos um ano.")
    first_year = as_of.year - years
    expected = pd.period_range(f"{first_year}-01", f"{as_of.year - 1}-12", freq="M")
    history = dividends.copy()
    history.index = pd.DatetimeIndex(history.index).to_period("M")
    if not history.index.is_unique:
        raise ValueError("Dividendos devem ter uma observação por mês.")
    values = history.reindex(expected)
    if values.isna().any():
        return None
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Dividendos inválidos.")
    annual = values.groupby(pd.PeriodIndex(values.index).year).sum()
    return float(np.average(annual.to_numpy(), weights=np.arange(1, years + 1)))


def radar(
    prices: pd.Series,
    dividends: pd.DataFrame,
    as_of: pd.Timestamp,
    buy_yield: float = 0.085,
    hold_yield: float = 0.06,
    base_weights: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Produz sinais de preço e pesos para novos recursos, sem vender posições."""
    if not 0 < hold_yield < buy_yield < 1:
        raise ValueError("Informe 0 < yield de manter < yield de comprar < 100%.")
    rows: list[dict[str, object]] = []
    for ticker, price in prices.items():
        symbol = str(ticker)
        dpa = weighted_dpa(dividends[symbol], as_of)
        signal = "SEM HISTÓRICO"
        buy = dpa / buy_yield if dpa is not None else None
        hold = dpa / hold_yield if dpa is not None else None
        if not np.isfinite(price) or price <= 0:
            signal = "SEM PREÇO"
        elif dpa == 0:
            signal = "SEM DIVIDENDOS"
        elif buy is not None and hold is not None:
            signal = "COMPRAR" if price <= buy else "MANTER" if price <= hold else "AGUARDAR"
        rows.append(
            {
                "ticker": symbol,
                "price": price,
                "dpa": dpa,
                "buy_ceiling": buy,
                "hold_ceiling": hold,
                "signal": signal,
            }
        )
    result = pd.DataFrame(rows).set_index("ticker")
    weights = pd.Series({t: (base_weights or {}).get(str(t), 1.0) for t in prices.index})
    if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
        raise ValueError("Pesos devem ser finitos, não negativos e ter soma positiva.")
    eligible = result["signal"].isin(["COMPRAR", "MANTER"])
    weights = weights.where(eligible, 0.0)
    result["allocation"] = weights / weights.sum() if weights.sum() > 0 else 0.0
    return result
