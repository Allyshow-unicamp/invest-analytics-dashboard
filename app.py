"""Entry point: streamlit run app.py."""

import streamlit as st

from services.logging_config import configure_logging
from ui.dashboard import render_dashboard
from ui.theme import apply_theme
from ui.views.rebalance_view import render_rebalance_view

st.set_page_config(page_title="Invest Analytics | Risco & Retorno", page_icon="📈", layout="wide")
configure_logging()
apply_theme()
view = st.sidebar.radio(
    "Área de trabalho", ["Dashboard analítico", "Simulador de aportes B3"], key="workspace_view"
)
if view == "Simulador de aportes B3":
    render_rebalance_view()
else:
    render_dashboard()
