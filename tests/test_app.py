"""Testes do fluxo Streamlit em headless, incluindo falhas de fonte."""

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from data.models import DataError

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_default_dashboard_and_empty_portfolio() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert len(app.tabs) == 5
    assert len(app.metric) >= 5
    assert len(app.get("plotly_chart")) >= 6
    app.multiselect("tickers").set_value([])
    app.button[0].click().run()
    assert not app.exception
    assert any("ao menos um ativo" in message.value for message in app.warning)


def test_us_market_and_zero_capital() -> None:
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.selectbox("market").set_value("EUA · USD").run()
    assert not app.exception
    assert any("USD" in message.value for message in app.caption)
    app.number_input("capital").set_value(0)
    app.number_input("contribution").set_value(0)
    app.button[0].click().run()
    assert not app.exception
    assert any("maior que zero" in message.value for message in app.warning)


def test_live_failure_shows_error_without_synthetic_fallback() -> None:
    with patch("ui.dashboard.YahooBCBProvider.load", side_effect=DataError("Fonte indisponível")):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        app.selectbox("source").set_value("Mercado (Yahoo + BCB)").run()
    assert not app.exception
    assert any("Fonte indisponível" in message.value for message in app.error)
    assert len(app.metric) == 0
