"""Contrato compartilhado entre fontes reais, demonstração e serviços."""

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


class DataError(ValueError):
    """Falha de qualidade ou indisponibilidade da fonte financeira."""


@dataclass(frozen=True)
class MarketData:
    """Séries mensais na mesma moeda, com proventos separados dos preços."""

    prices: pd.DataFrame
    adjusted_prices: pd.DataFrame
    dividends: pd.DataFrame
    benchmark: pd.Series
    cash_returns: pd.Series
    currency: str
    source: str
    benchmark_name: str
    notes: tuple[str, ...] = ()


class MarketProvider(Protocol):
    """Porta de entrada substituível sem alterações no motor financeiro."""

    def load(self, tickers: tuple[str, ...], start: str, end: str, market: str) -> MarketData:
        """Carrega meses completos entre start e end inclusivos."""
        ...
