"""Entry point: streamlit run app.py."""

from services.logging_config import configure_logging
from ui.dashboard import render_dashboard

configure_logging()
render_dashboard()
