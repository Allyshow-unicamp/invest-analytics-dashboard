"""Contratos de cotações, falhas e validação do caso de uso antes da rede."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from core.allocation import AllocationStrategy
from data.b3_market import DemoB3Provider, YahooB3Provider, aligned_daily_returns
from data.models import DataError
from services.allocation import parse_positions, simulate_contribution
from ui.views.rebalance_view import initial_portfolio


def test_demo_supports_stocks_fiis_and_etfs() -> None:
    positions = parse_positions(initial_portfolio())
    result = simulate_contribution(positions, 5000, AllocationStrategy.REBALANCE, DemoB3Provider())
    assert set(result.result.orders.index) == {"ITUB4.SA", "HGLG11.SA", "BOVA11.SA"}
    assert result.result.observations >= 60
    assert result.result.allocated + result.result.residual_cash == pytest.approx(5000)


def test_invalid_targets_do_not_trigger_provider() -> None:
    frame = initial_portfolio()
    frame.loc[0, "target_percent"] = 90
    with pytest.raises(ValueError, match="100%"):
        parse_positions(frame)


def test_daily_history_rejects_internal_gaps() -> None:
    frame = pd.DataFrame({"ITUB4.SA": np.arange(70) + 10.0}, index=pd.bdate_range("2024-01-01", periods=70))
    frame.iloc[35, 0] = np.nan
    with pytest.raises(DataError, match="lacunas"):
        aligned_daily_returns(frame)


def test_yahoo_quotes_are_unadjusted_with_timestamp() -> None:
    index = pd.DatetimeIndex([pd.Timestamp.now(tz="America/Sao_Paulo").floor("min")])
    frame = pd.DataFrame({"Close": [34.2]}, index=index)
    with patch("data.b3_market.yf.Ticker") as ticker:
        ticker.return_value.history.return_value = frame
        quote = YahooB3Provider()._quote("ITUB4.SA")
    assert quote.price == 34.2
    assert quote.as_of.tzinfo is not None
    assert ticker.return_value.history.call_args.kwargs["auto_adjust"] is False


def test_daily_fallback_is_explicit() -> None:
    index = pd.DatetimeIndex([pd.Timestamp.now(tz="America/Sao_Paulo").normalize()])
    with patch("data.b3_market.yf.Ticker") as ticker:
        ticker.return_value.history.side_effect = [
            pd.DataFrame(),
            pd.DataFrame({"Close": [34.0]}, index=index),
        ]
        quote = YahooB3Provider()._quote("ITUB4.SA")
    assert quote.kind == "Último fechamento diário"


def test_missing_history_keeps_quotes_and_non_risk_plan_available() -> None:
    demo = DemoB3Provider().load(("ITUB4",))
    with (
        patch.object(YahooB3Provider, "_quote", return_value=demo.quotes[0]),
        patch.object(YahooB3Provider, "_history", side_effect=DataError("sem histórico")),
    ):
        provider = YahooB3Provider()
        from data.b3_market import HISTORY_CACHE

        HISTORY_CACHE.clear()
        snapshot = provider.load(("ITUB4",))
    assert snapshot.quotes
    assert snapshot.returns is None
    assert "sem histórico" in snapshot.notes[0]
