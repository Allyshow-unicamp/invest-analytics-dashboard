"""Fixtures sem rede com preços e dividendos em frequência mensal."""

import pandas as pd
import pytest

from data.demo import DemoProvider
from data.models import MarketData


@pytest.fixture
def market_data() -> MarketData:
    return DemoProvider().load(("ITUB4.SA", "BBAS3.SA"), "2010-01-01", "2025-12-31", "B3")


@pytest.fixture
def dates() -> pd.DatetimeIndex:
    return pd.date_range("2020-01-31", periods=3, freq="ME")
