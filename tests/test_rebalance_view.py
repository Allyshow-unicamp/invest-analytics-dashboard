"""Fluxos da nova visão sem chamadas externas e regressão da navegação."""

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from data.b3_market import DemoB3Provider
from ui.views.rebalance_view import initial_portfolio

APP = Path(__file__).resolve().parents[1] / "app.py"


def simulator() -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.radio("workspace_view").set_value("Simulador de aportes B3").run()
    assert not app.exception
    return app


def test_form_does_not_fetch_until_submission_and_keeps_dashboard() -> None:
    with patch(
        "ui.views.rebalance_view.DemoB3Provider.load",
        wraps=DemoB3Provider().load,
    ) as load:
        app = simulator()
        load.assert_not_called()
        app.button("allocation_submit").click().run()
        assert not app.exception
        assert load.call_count == 1
    assert len(app.get("plotly_chart")) == 2
    orders = [table.value for table in app.dataframe if "Cotas a comprar" in table.value.columns][0]
    assert (orders["Cotas a comprar"] >= 0).all()
    app.radio("workspace_view").set_value("Dashboard analítico").run()
    assert not app.exception
    assert len(app.tabs) == 5


@pytest.mark.parametrize("criterion", ["Variância mínima", "Sharpe máximo"])
def test_risk_strategies_render_without_error(criterion: str) -> None:
    app = simulator()
    app.selectbox("allocation_strategy").set_value("Otimização de risco e retorno")
    app.selectbox("allocation_criterion").set_value(criterion)
    app.button("allocation_submit").click().run()
    assert not app.exception
    assert not app.error
    assert len(app.metric) == 6


def test_invalid_targets_show_error_before_any_market_query() -> None:
    table = initial_portfolio()
    table.loc[0, "target_percent"] = 80
    with (
        patch("ui.views.rebalance_view.initial_portfolio", return_value=table),
        patch("ui.views.rebalance_view.YahooB3Provider.load") as load,
    ):
        app = simulator()
        app.selectbox("allocation_source").set_value("Yahoo Finance · B3")
        app.button("allocation_submit").click().run()
        load.assert_not_called()
    assert not app.exception
    assert any("100%" in error.value for error in app.error)
