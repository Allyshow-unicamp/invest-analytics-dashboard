"""Cotações recentes e retornos diários ajustados para o simulador B3."""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Protocol, cast

import numpy as np
import pandas as pd
import yfinance as yf
from numpy.typing import NDArray

from core.allocation import normalize_b3_ticker
from core.metrics import price_returns
from data.cache import TTLCache
from data.fetcher import extract_field, retry_call
from data.models import DataError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketQuote:
    """Preço de referência e horário informado pela fonte, sem promessa de latência."""

    ticker: str
    price: float
    as_of: datetime
    kind: str


@dataclass(frozen=True)
class B3Snapshot:
    """Cotações para as ordens e amostra comum para comparação de risco."""

    quotes: tuple[MarketQuote, ...]
    returns: pd.DataFrame | None
    source: str
    notes: tuple[str, ...] = ()


class B3Provider(Protocol):
    """Contrato substituível para o caso de uso de aporte imediato."""

    def load(self, tickers: tuple[str, ...], years: int = 3, fresh_quotes: bool = True) -> B3Snapshot:
        """Retorna cotações em BRL e retornos totais diários."""
        ...


QUOTE_CACHE: TTLCache[MarketQuote] = TTLCache(ttl=60, max_entries=100)
HISTORY_CACHE: TTLCache[pd.DataFrame] = TTLCache(ttl=3600, max_entries=16)


def _symbols(tickers: tuple[str, ...], years: int) -> tuple[str, ...]:
    result = tuple(normalize_b3_ticker(t) for t in tickers)
    if not result or len(result) > 30 or len(set(result)) != len(result):
        raise DataError("Informe de 1 a 30 ativos B3 únicos.")
    if years not in {1, 3, 5}:
        raise DataError("A janela histórica deve ser de 1, 3 ou 5 anos.")
    return result


def aligned_daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Recorta bordas de listagens; recusa lacunas internas e séries inválidas."""
    if prices.empty or prices.isna().all().any() or prices.columns.duplicated().any():
        raise DataError("Histórico ausente para um dos ativos.")
    observed = prices.to_numpy(dtype=float)
    present = observed[~np.isnan(observed)]
    if not np.isfinite(present).all() or (present <= 0).any():
        raise DataError("Preços históricos inválidos.")
    starts = [pd.Timestamp(prices[column].dropna().index[0]) for column in prices]
    ends = [pd.Timestamp(prices[column].dropna().index[-1]) for column in prices]
    common = prices.loc[max(starts) : min(ends)]
    if common.isna().any().any() or len(common) < 61:
        raise DataError("São necessários 60 retornos diários comuns, sem lacunas internas.")
    return price_returns(common)


class YahooB3Provider:
    """Consulta preço intradiário, com fallback explícito ao último fechamento."""

    def load(self, tickers: tuple[str, ...], years: int = 3, fresh_quotes: bool = True) -> B3Snapshot:
        symbols = _symbols(tickers, years)
        quotes = tuple(
            self._quote(t) if fresh_quotes else QUOTE_CACHE.get_or_load(t, partial(self._quote, t))
            for t in symbols
        )
        notes: tuple[str, ...] = ()
        returns = None
        try:
            key = f"{','.join(symbols)}|{years}|{pd.Timestamp.now(tz='America/Sao_Paulo'):%Y-%m-%d}"
            returns = HISTORY_CACHE.get_or_load(key, lambda: self._history(symbols, years))
        except DataError as exc:
            notes = (f"Impacto de risco indisponível: {exc}",)
        return B3Snapshot(quotes, returns, "Yahoo Finance · última cotação disponível", notes)

    def _quote(self, ticker: str) -> MarketQuote:
        def fetch() -> MarketQuote:
            try:
                stock = yf.Ticker(ticker)
                frame = stock.history(period="5d", interval="1m", auto_adjust=False, actions=False)
                kind = "Intradiária"
                if frame is None or frame.empty:
                    frame = stock.history(period="5d", interval="1d", auto_adjust=False, actions=False)
                    kind = "Último fechamento diário"
                if frame is None or frame.empty or "Close" not in frame:
                    raise DataError(f"Sem cotação disponível para {ticker}.")
                closes = frame["Close"].dropna()
                if closes.empty:
                    raise DataError(f"Sem cotação válida para {ticker}.")
                price = float(closes.iloc[-1])
                timestamp = pd.Timestamp(closes.index[-1])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize("America/Sao_Paulo")
                timestamp = timestamp.tz_convert("America/Sao_Paulo")
                age = pd.Timestamp.now(tz="America/Sao_Paulo") - timestamp
                if (
                    not np.isfinite(price)
                    or price <= 0
                    or age > pd.Timedelta(days=7)
                    or age < pd.Timedelta(minutes=-5)
                ):
                    raise DataError(f"Cotação inválida ou desatualizada para {ticker}.")
                return MarketQuote(ticker, price, timestamp.to_pydatetime(), kind)
            except Exception as exc:
                if isinstance(exc, DataError):
                    raise
                raise DataError(f"Falha ao consultar {ticker} no Yahoo Finance.") from exc

        return retry_call(fetch)

    def _history(self, symbols: tuple[str, ...], years: int) -> pd.DataFrame:
        def fetch() -> pd.DataFrame:
            try:
                today = pd.Timestamp.now(tz="America/Sao_Paulo").normalize().tz_localize(None)
                raw = yf.download(
                    list(symbols),
                    start=(today - pd.DateOffset(years=years)).strftime("%Y-%m-%d"),
                    end=today.strftime("%Y-%m-%d"),
                    auto_adjust=True,
                    interval="1d",
                    progress=False,
                    threads=False,
                    timeout=15,
                )
                if raw is None or raw.empty:
                    raise DataError("Yahoo Finance não devolveu o histórico diário.")
                return aligned_daily_returns(extract_field(cast(pd.DataFrame, raw), "Close", symbols))
            except Exception as exc:
                if isinstance(exc, DataError):
                    raise
                raise DataError("Falha no histórico diário do Yahoo Finance.") from exc

        return retry_call(fetch)


class DemoB3Provider:
    """Cotações e retornos fictícios, determinísticos por ticker e sem rede."""

    def load(self, tickers: tuple[str, ...], years: int = 3, fresh_quotes: bool = True) -> B3Snapshot:
        symbols = _symbols(tickers, years)
        count = years * 252 + 1
        index = pd.bdate_range(end="2025-12-31", periods=count)
        common = np.random.default_rng(42).normal(0.0003, 0.009, count)
        quotes: list[MarketQuote] = []
        prices: dict[str, NDArray[np.float64]] = {}
        defaults = {"ITUB4.SA": 34.0, "HGLG11.SA": 160.0, "BOVA11.SA": 125.0}
        for symbol in symbols:
            seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            returns = np.clip(common * rng.uniform(0.5, 1.2) + rng.normal(0.0001, 0.007, count), -0.3, 0.3)
            price = defaults.get(symbol, round(10 + seed % 19000 / 100, 2))
            prices[symbol] = 100 * np.cumprod(1 + returns)
            quotes.append(
                MarketQuote(
                    symbol,
                    price,
                    pd.Timestamp("2025-12-31 17:00", tz="America/Sao_Paulo").to_pydatetime(),
                    "Sintética",
                )
            )
        return B3Snapshot(
            tuple(quotes),
            aligned_daily_returns(pd.DataFrame(prices, index=index)),
            "Demonstração · preços e histórico sintéticos",
            ("Os tickers são exemplos; preços e riscos deste modo são fictícios.",),
        )
