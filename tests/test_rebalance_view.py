"""Fluxos da visão de aportes com base nas ações COMPRAR do Radar Bazin."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data.b3_market import DemoB3Provider
from data.demo import DemoProvider
from ui.views.rebalance_view import initial_portfolio, radar_buy_portfolio

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(autouse=True)
def mock_market_providers() -> object:
    with patch("ui.dashboard.YahooBCBProvider.load", side_effect=DemoProvider().load):
        yield


def simulator() -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.radio("workspace_view").set_value("Simulador de aportes B3").run()
    assert not app.exception
    return app


def test_radar_buy_portfolio_filters_only_buy_signals_and_sums_to_100() -> None:
    radar = pd.DataFrame(
        {
            "price": [36.0, 28.0, 45.0],
            "signal": ["AGUARDAR", "COMPRAR", "COMPRAR"],
        },
        index=["ITUB4.SA", "BBAS3.SA", "TAEE11.SA"],
    )
    portfolio = radar_buy_portfolio(radar)
    assert portfolio is not None
    assert portfolio["ticker"].tolist() == ["BBAS3", "TAEE11"]
    assert portfolio["target_percent"].sum() == pytest.approx(100.0)


def test_form_uses_radar_buy_stocks_and_does_not_fetch_until_submission() -> None:
    with patch(
        "ui.views.rebalance_view.YahooB3Provider.load",
        wraps=DemoB3Provider().load,
    ) as load:
        app = simulator()
        load.assert_not_called()
        app.button("allocation_submit").click().run()
        assert not app.exception
        assert load.call_count == 1
        called_tickers = load.call_args.args[0]
        assert called_tickers == ("EQTL3.SA", "LREN3.SA")
    assert len(app.get("plotly_chart")) == 2
    orders = [table.value for table in app.dataframe if "Cotas a comprar" in table.value.columns][0]
    assert (orders["Cotas a comprar"] >= 0).all()
    app.radio("workspace_view").set_value("Dashboard analítico").run()
    assert not app.exception
    assert len(app.tabs) == 5


@pytest.mark.parametrize("criterion", ["Variância mínima", "Sharpe máximo"])
def test_risk_strategies_render_without_error(criterion: str) -> None:
    with patch("ui.views.rebalance_view.YahooB3Provider.load", wraps=DemoB3Provider().load):
        app = simulator()
        app.selectbox("allocation_strategy").set_value("Otimização de risco e retorno")
        app.selectbox("allocation_criterion").set_value(criterion)
        app.button("allocation_submit").click().run()
    assert not app.exception
    assert not app.error
    assert len(app.metric) == 6


def test_invalid_targets_show_error_before_any_market_query() -> None:
    table = initial_portfolio(pd.DataFrame())
    table.loc[0, "target_percent"] = 80
    with (
        patch("ui.views.rebalance_view.radar_buy_portfolio", return_value=table),
        patch("ui.views.rebalance_view.YahooB3Provider.load") as load,
    ):
        app = simulator()
        app.button("allocation_submit").click().run()
        load.assert_not_called()
    assert not app.exception
    assert any("100%" in error.value for error in app.error)
