"""Yahoo Finance/BCB com retries, cache e validação sem preços inventados."""

import json
import logging
import time
from collections.abc import Callable
from typing import TypeVar, cast

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data.cache import TTLCache
from data.models import DataError, MarketData

logger = logging.getLogger(__name__)
T = TypeVar("T")
CACHE: TTLCache[MarketData] = TTLCache()


def retry_call(loader: Callable[[], T], attempts: int = 3) -> T:
    """Repete falhas transitórias; registra contexto sem credenciais."""
    for attempt in range(attempts):
        try:
            return loader()
        except (DataError, requests.RequestException, OSError) as exc:
            logger.warning(
                json.dumps(
                    {"event": "provider_retry", "attempt": attempt + 1, "error_type": type(exc).__name__}
                )
            )
            if attempt + 1 == attempts:
                raise DataError("Fonte indisponível após novas tentativas. Use o modo demonstração.") from exc
            time.sleep(0.5 * 2**attempt)
    raise ValueError("Número de tentativas deve ser positivo.")


def extract_field(raw: pd.DataFrame, field: str, tickers: tuple[str, ...]) -> pd.DataFrame:
    """Aceita colunas simples ou MultiIndex nas duas orientações do Yahoo."""
    if raw.empty:
        raise DataError("Yahoo Finance retornou uma tabela vazia.")
    result: pd.DataFrame | pd.Series
    if isinstance(raw.columns, pd.MultiIndex):
        levels = [
            level for level in range(raw.columns.nlevels) if field in raw.columns.get_level_values(level)
        ]
        if len(levels) != 1:
            raise DataError(f"Campo obrigatório ausente ou ambíguo: {field}.")
        result = raw.xs(field, level=levels[0], axis=1)
    else:
        if field not in raw.columns or len(tickers) != 1:
            raise DataError(f"Campo obrigatório ausente: {field}.")
        result = raw[field].to_frame(name=tickers[0])
    if isinstance(result, pd.Series):
        result = result.to_frame(name=tickers[0])
    if not set(tickers).issubset(result.columns):
        raise DataError(f"Tickers ausentes na resposta de {field}.")
    result = result.loc[:, list(tickers)].apply(pd.to_numeric, errors="coerce")
    result.index = pd.DatetimeIndex(pd.to_datetime(result.index)).tz_localize(None).normalize()
    return cast(pd.DataFrame, result.loc[~result.index.duplicated(keep="last")].sort_index())


def clean_prices(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Rejeita valores inválidos e lacunas internas; sinaliza movimentos extremos.

    Recorta somente as bordas para a interseção dos históricos. Outliers de
    mercado permanecem nos cálculos, pois podem representar crises reais.
    """
    if frame.empty or frame.columns.duplicated().any() or not isinstance(frame.index, pd.DatetimeIndex):
        raise DataError("Tabela vazia ou com ativos duplicados.")
    frame = frame.sort_index().copy()
    if not frame.index.is_unique:
        raise DataError("Preços com datas duplicadas.")
    values = frame.to_numpy(dtype=float)
    observed = values[~np.isnan(values)]
    if not np.isfinite(observed).all() or (observed <= 0).any():
        raise DataError("Preços não positivos ou não finitos na fonte.")
    if frame.isna().all().any():
        raise DataError("Ao menos um ativo não possui histórico.")
    starts = [pd.DatetimeIndex(frame[c].dropna().index)[0] for c in frame]
    ends = [pd.DatetimeIndex(frame[c].dropna().index)[-1] for c in frame]
    common_start, common_end = max(starts), min(ends)
    aligned = frame.loc[common_start:common_end]
    if len(aligned) < 3:
        raise DataError("Histórico comum insuficiente: selecione outros ativos ou datas.")
    if aligned.isna().any().any():
        raise DataError("Lacuna interna de preços. Nenhum preço foi preenchido automaticamente.")
    expected = pd.period_range(aligned.index[0], aligned.index[-1], freq="M")
    if not pd.DatetimeIndex(aligned.index).to_period("M").equals(expected):
        raise DataError("Faltam meses no histórico de preços.")
    notes: list[str] = []
    if len(aligned) != len(frame):
        notes.append("Janela recortada para o histórico comum dos ativos e do benchmark.")
    jumps = aligned.pct_change(fill_method=None).abs() > 0.5
    if jumps.any().any():
        notes.append("Variação mensal acima de 50% detectada; preservada para revisão da fonte.")
    return aligned, tuple(notes)


def monthly_cdi(daily_percent: pd.Series) -> pd.Series:
    """Compõe SGS 12 (% a.d.) em retorno mensal fracionário."""
    if daily_percent.empty or not np.isfinite(daily_percent).all() or (daily_percent < 0).any():
        raise DataError("CDI diário ausente ou inválido.")
    return ((1 + daily_percent / 100).resample("ME").prod(min_count=1) - 1).rename("CDI")


class YahooBCBProvider:
    """Adaptador real: preços/proventos Yahoo e CDI SGS 12, sem chave de API."""

    def load(self, tickers: tuple[str, ...], start: str, end: str, market: str) -> MarketData:
        """Carrega dados e armazena apenas respostas completas e válidas."""
        if not tickers or len(set(tickers)) != len(tickers) or market not in {"B3", "EUA"}:
            raise DataError("Selecione ativos únicos e um mercado válido.")
        if pd.Timestamp(start) >= pd.Timestamp(end):
            raise DataError("A data inicial deve anteceder a final.")
        key = json.dumps(["monthly-v1", tickers, start, end, market])
        return CACHE.get_or_load(key, lambda: self._download(tickers, start, end, market))

    def _download(self, tickers: tuple[str, ...], start: str, end: str, market: str) -> MarketData:
        benchmark_symbol = "^BVSP" if market == "B3" else "VOO"
        symbols = tuple(dict.fromkeys((*tickers, benchmark_symbol)))
        exclusive_end = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        def download() -> pd.DataFrame:
            response = yf.download(
                list(symbols),
                start=start,
                end=exclusive_end,
                interval="1d",
                auto_adjust=False,
                actions=True,
                progress=False,
                threads=False,
                timeout=15,
                keepna=True,
            )
            if response is None or response.empty:
                raise DataError("Yahoo Finance sem resposta.")
            # Downloads parciais também devem ser repetidos.
            close = extract_field(response, "Close", symbols)
            if close.isna().all().any():
                raise DataError("Download parcial do Yahoo Finance.")
            return cast(pd.DataFrame, response)

        raw = retry_call(download)
        closes = extract_field(raw, "Close", symbols).resample("ME").last()
        adjusted = extract_field(raw, "Adj Close", symbols).resample("ME").last()
        dividends_daily = extract_field(raw, "Dividends", symbols)
        price_daily = extract_field(raw, "Close", symbols)
        # Só dias com negociação podem transformar ausência de evento em zero.
        if (dividends_daily.isna() & price_daily.notna()).any().any():
            raise DataError("Campo de dividendos incompleto em dia com cotação.")
        dividends = dividends_daily.where(price_daily.notna()).resample("ME").sum(min_count=1)
        # Mês corrente e mês final parcial não entram nas métricas mensais.
        last_complete = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).normalize().replace(day=1)
        inclusive_end = pd.Timestamp(end).normalize()
        closes = closes.loc[(closes.index < last_complete) & (closes.index <= inclusive_end)]
        adjusted = adjusted.reindex(closes.index)
        dividends = dividends.reindex(closes.index)
        benchmark = adjusted[benchmark_symbol] if market == "EUA" else closes[benchmark_symbol]
        combined = closes[list(tickers)].copy()
        combined["__benchmark__"] = benchmark
        aligned, notes = clean_prices(combined)
        selected = aligned.index
        adjusted_selected = adjusted.loc[selected, list(tickers)]
        if not np.isfinite(adjusted_selected.to_numpy()).all() or (adjusted_selected <= 0).any().any():
            raise DataError("Preços ajustados ausentes ou inválidos.")
        if market == "B3":
            cash = self._cdi(start, end).reindex(selected)
            if cash.isna().any():
                raise DataError("CDI não cobre todos os meses do histórico comum.")
        else:
            cash = pd.Series(0.0, index=selected, name="Caixa USD (0%)")
            notes += ("Caixa USD sem remuneração. Sharpe usa a taxa anual USD informada na interface.",)
        logger.info(
            json.dumps(
                {"event": "market_loaded", "market": market, "assets": len(tickers), "months": len(selected)}
            )
        )
        return MarketData(
            prices=aligned[list(tickers)],
            adjusted_prices=adjusted_selected,
            dividends=dividends[list(tickers)],
            benchmark=benchmark.loc[selected],
            cash_returns=cash,
            currency="BRL" if market == "B3" else "USD",
            source="Yahoo Finance + BCB" if market == "B3" else "Yahoo Finance",
            benchmark_name="Ibovespa" if market == "B3" else "VOO (retorno total)",
            notes=notes,
        )

    def _cdi(self, start: str, end: str) -> pd.Series:
        pieces: list[pd.Series] = []
        session = requests.Session()
        session.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
            ),
        )
        cursor, limit = pd.Timestamp(start), pd.Timestamp(end)
        try:
            while cursor <= limit:
                stop = min(cursor + pd.DateOffset(years=5) - pd.Timedelta(days=1), limit)
                response = session.get(
                    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados",
                    params={
                        "formato": "json",
                        "dataInicial": cursor.strftime("%d/%m/%Y"),
                        "dataFinal": stop.strftime("%d/%m/%Y"),
                    },
                    timeout=20,
                )
                response.raise_for_status()
                records = pd.DataFrame(response.json())
                if not {"data", "valor"}.issubset(records.columns):
                    raise DataError("Resposta SGS sem datas/valores.")
                series = pd.Series(
                    pd.to_numeric(records["valor"], errors="coerce").to_numpy(),
                    index=pd.to_datetime(records["data"], format="%d/%m/%Y"),
                )
                pieces.append(series)
                cursor = stop + pd.Timedelta(days=1)
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise DataError("Não foi possível carregar o CDI do Banco Central.") from exc
        finally:
            session.close()
        daily = pd.concat(pieces).sort_index()
        return monthly_cdi(daily.loc[~daily.index.duplicated(keep="last")])
