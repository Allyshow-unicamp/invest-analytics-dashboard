"""Contratos de ingestão, cache e limpeza; nenhuma requisição externa."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from data.cache import TTLCache
from data.fetcher import CACHE, YahooBCBProvider, clean_prices, extract_field, monthly_cdi
from data.models import DataError


@pytest.mark.parametrize("reverse", [False, True])
def test_yahoo_multiindex_orientations(reverse: bool) -> None:
    columns = pd.MultiIndex.from_product([["Close", "Adj Close", "Dividends"], ["A", "B"]])
    raw = pd.DataFrame([[10, 20, 10, 20, 0, 0]], columns=columns, index=[pd.Timestamp("2020-01-31")])
    if reverse:
        raw.columns = raw.columns.swaplevel()
    assert extract_field(raw, "Close", ("A", "B")).iloc[0].tolist() == [10, 20]


def test_single_ticker_and_missing_field() -> None:
    raw = pd.DataFrame({"Close": [10]}, index=[pd.Timestamp("2020-01-31")])
    assert extract_field(raw, "Close", ("A",)).columns.tolist() == ["A"]
    with pytest.raises(DataError):
        extract_field(raw, "Dividends", ("A",))


def test_no_backward_fill_before_listing() -> None:
    index = pd.date_range("2020-01-31", periods=4, freq="ME")
    cleaned, notes = clean_prices(
        pd.DataFrame({"A": [10, 11, 12, 13], "B": [np.nan, 10, 11, 12]}, index=index)
    )
    assert cleaned.index[0] == index[1]
    assert notes


@pytest.mark.parametrize("values", [[10, np.nan, 12, 13], [10, 0, 12, 13], [10, np.inf, 12, 13]])
def test_bad_prices_are_rejected(values: list[float]) -> None:
    frame = pd.DataFrame({"A": values}, index=pd.date_range("2020-01-31", periods=4, freq="ME"))
    with pytest.raises(DataError):
        clean_prices(frame)


def test_extreme_returns_are_flagged_and_preserved() -> None:
    frame = pd.DataFrame({"A": [10, 20, 15]}, index=pd.date_range("2020-01-31", periods=3, freq="ME"))
    cleaned, notes = clean_prices(frame)
    pd.testing.assert_frame_equal(cleaned, frame)
    assert "50%" in notes[0]


def test_cdi_percent_to_fraction_is_compounded() -> None:
    daily = pd.Series([1.0, 1.0], index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    assert monthly_cdi(daily).iloc[0] == pytest.approx(0.0201)


def test_cache_ttl_isolation_and_exception_policy() -> None:
    cache: TTLCache[list[int]] = TTLCache(ttl=10)
    value = [1]
    with patch("data.cache.time.monotonic", return_value=0):
        result = cache.get_or_load("A", lambda: value)
        result.append(2)
        assert cache.get_or_load("A", lambda: [3]) == [1]
    with patch("data.cache.time.monotonic", return_value=11):
        assert cache.get_or_load("A", lambda: [4]) == [4]
    with pytest.raises(DataError):
        cache.get_or_load("failure", lambda: (_ for _ in ()).throw(DataError("offline")))
    assert cache.get_or_load("failure", lambda: [5]) == [5]


def test_provider_uses_explicit_adjustment_and_end_exclusive() -> None:
    dates = pd.date_range("2020-01-31", periods=4, freq="ME")
    symbols = ("A", "SPY")
    columns = pd.MultiIndex.from_product([["Close", "Adj Close", "Dividends"], symbols])
    raw = pd.DataFrame([[10, 20, 10, 20, 0, 0]] * 4, index=dates, columns=columns)
    CACHE.clear()
    with patch("data.fetcher.yf.download", return_value=raw) as download:
        data = YahooBCBProvider().load(("A",), "2020-01-01", "2020-04-30", "EUA")
    assert download.call_args.kwargs["end"] == "2020-05-01"
    assert download.call_args.kwargs["auto_adjust"] is False
    assert data.currency == "USD"
    assert (data.cash_returns == 0).all()
    assert data.prices.shape == (4, 1)
    CACHE.clear()
