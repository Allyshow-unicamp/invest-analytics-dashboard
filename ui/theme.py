"""Identidade visual compartilhada pelas áreas de trabalho Streamlit."""

from html import escape

import streamlit as st

CSS = """<style>
    .block-container {padding-top: 3rem; max-width: 1600px;}
    h1 {letter-spacing: -0.04em; font-weight: 800;}
    h2, h3 {letter-spacing: -0.02em;}

    /* Cartões de métricas */
    [data-testid="stMetric"] {
        background: linear-gradient(160deg, #15233a 0%, #101a2b 100%);
        border-color: #23334c !important;
        border-radius: 14px;
        transition: border-color .2s ease, transform .2s ease;
    }
    [data-testid="stMetric"]:hover {border-color: #38d6bd !important; transform: translateY(-2px);}
    [data-testid="stMetricLabel"] p {
        text-transform: uppercase; letter-spacing: .06em; font-size: .74rem; color: #8fa3bf;
    }
    [data-testid="stMetricValue"] {font-size: 1.45rem; font-weight: 700;}
    @media (max-width: 1400px) {[data-testid="stMetricValue"] {font-size: 1.15rem;}}
    .st-key-portfolio_metrics [data-testid="stHorizontalBlock"] {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.75rem;
    }
    .st-key-portfolio_metrics [data-testid="stColumn"] {width: 100% !important; min-width: 0 !important;}

    /* Abas */
    [data-baseweb="tab-list"] {gap: 1.25rem; border-bottom: 1px solid #23334c;}
    [data-baseweb="tab"] p {font-size: 1rem; font-weight: 600;}

    /* Barra lateral */
    [data-testid="stSidebar"] {border-right: 1px solid #23334c;}
    .ia-brand {display: flex; align-items: center; gap: .6rem; margin: -1.5rem 0 1.25rem;}
    .ia-brand-logo {
        width: 38px; height: 38px; border-radius: 10px; display: grid; place-items: center;
        background: linear-gradient(135deg, #38d6bd, #70aaff); color: #0c1422; font-weight: 800;
    }
    .ia-brand-name {font-weight: 800; font-size: 1.05rem; line-height: 1.1;}
    .ia-brand-tag {font-size: .72rem; color: #8fa3bf; letter-spacing: .05em; text-transform: uppercase;}

    /* Hero e resumo executivo */
    .ia-eyebrow {color: #38d6bd; font-size: .78rem; letter-spacing: .14em; font-weight: 700;}
    .ia-chips {display: flex; flex-wrap: wrap; gap: .5rem; margin: .25rem 0 1rem;}
    .ia-chip {
        border: 1px solid #23334c; background: #131f31; border-radius: 999px;
        padding: .2rem .75rem; font-size: .8rem; color: #b8c6d9;
    }
    .ia-chip-demo {border-color: #70aaff; color: #9cc3ff; background: rgba(112,170,255,.08);}
    .ia-summary {
        border: 1px solid #23334c; border-left: 4px solid #38d6bd; border-radius: 14px;
        background: linear-gradient(120deg, rgba(56,214,189,.09), rgba(112,170,255,.04));
        padding: 1.1rem 1.4rem; margin: .5rem 0 1.25rem; font-size: 1.05rem; line-height: 1.6;
    }
    .ia-summary-title {
        font-size: .75rem; letter-spacing: .12em; text-transform: uppercase; color: #38d6bd;
        font-weight: 700; margin-bottom: .35rem;
    }
    .ia-summary b {color: #ffffff;}
    .ia-up {color: #38d6bd; font-weight: 700;}
    .ia-down {color: #fb809b; font-weight: 700;}
</style>"""


def apply_theme() -> None:
    """Injeta o CSS global e a marca na barra lateral."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.sidebar.markdown(
        """<div class="ia-brand"><div class="ia-brand-logo">IA</div><div>
        <div class="ia-brand-name">Invest Analytics</div>
        <div class="ia-brand-tag">Risco · Retorno · Dividendos</div></div></div>""",
        unsafe_allow_html=True,
    )


def hero(eyebrow: str, title: str, subtitle: str) -> None:
    """Cabeçalho de página com hierarquia tipográfica consistente."""
    st.markdown(f'<div class="ia-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.write(subtitle)


def chips(items: list[str], demo: bool = False) -> None:
    """Contexto da análise em etiquetas compactas, em vez de vários avisos."""
    tags = ['<span class="ia-chip ia-chip-demo">DEMONSTRAÇÃO · dados sintéticos</span>'] if demo else []
    tags += [f'<span class="ia-chip">{escape(item)}</span>' for item in items]
    st.markdown(f'<div class="ia-chips">{"".join(tags)}</div>', unsafe_allow_html=True)
