"""Dados sintéticos reproduzíveis; nenhuma cotação é apresentada como real."""

import numpy as np
import pandas as pd

from core.bazin import B3_WEIGHTS
from data.models import DataError, MarketData

US_TICKERS = (
    "O",
    "CVX",
    "ED",
    "ADM",
    "XOM",
    "JNJ",
    "PEP",
    "KO",
    "PG",
    "ABT",
    "TGT",
    "LOW",
    "CL",
    "GWW",
    "EMR",
    "VOO",
    "SPY",
    "QQQ",
    "JEPQ",
)


class DemoProvider:
    """Gera o mesmo universo completo a cada execução, com seed fixa."""

    def load(self, tickers: tuple[str, ...], start: str, end: str, market: str) -> MarketData:
        """Fornece meses entre 2010 e 2025 sem acesso à rede ou arquivos locais."""
        universe = tuple(B3_WEIGHTS) if market == "B3" else US_TICKERS
        if not tickers or not set(tickers).issubset(universe):
            raise DataError("Ticker indisponível na demonstração.")
        index = pd.date_range("2010-01-31", "2025-12-31", freq="ME")
        rng = np.random.default_rng(42 if market == "B3" else 43)
        common = rng.normal(0.0065, 0.036, len(index))
        common[120:123] -= 0.075
        prices, dividends, adjusted = {}, {}, {}
        for i, ticker in enumerate(universe):
            overvalued = market == "B3" and i in (3, 7, 9, 11)
            drift = (0.0005 if overvalued else 0.0028) if market == "B3" else 0.0038
            r = np.clip(common * (0.7 + (i % 6) / 25) + rng.normal(drift, 0.022, len(index)), -0.65, 0.65)
            quotes = (20 + i * 4) * np.cumprod(1 + r)
            q_yield = (0.011 if overvalued else 0.028 - (i % 3) * 0.003) if market == "B3" else 0.011
            payments = np.where(index.month.isin([3, 6, 9, 12]), np.roll(quotes, 1) * q_yield, 0)
            payments[0] = 0
            total = (quotes[1:] + payments[1:]) / quotes[:-1]
            prices[ticker], dividends[ticker] = quotes, payments
            adjusted[ticker] = np.r_[quotes[0], quotes[0] * np.cumprod(total)]
        frame = pd.DataFrame(prices, index=index).loc[start:end, list(tickers)]
        if len(frame) < 3:
            raise DataError("Demonstração disponível entre janeiro/2010 e dezembro/2025.")
        bench_drift = 0.0038 if market == "B3" else 0.0052
        benchmark = pd.Series(100 * np.cumprod(1 + common + bench_drift), index=index).loc[frame.index]
        cash = (1.095 ** (1 / 12) - 1) if market == "B3" else 0.0
        return MarketData(
            prices=frame,
            adjusted_prices=pd.DataFrame(adjusted, index=index).loc[frame.index, list(tickers)],
            dividends=pd.DataFrame(dividends, index=index).loc[frame.index, list(tickers)],
            benchmark=benchmark,
            cash_returns=pd.Series(cash, index=frame.index),
            currency="BRL" if market == "B3" else "USD",
            source="Demonstração sintética · seed 42/43",
            benchmark_name="Ibovespa sintético" if market == "B3" else "VOO sintético",
            notes=("Todos os dados deste modo são simulados.",),
        )
