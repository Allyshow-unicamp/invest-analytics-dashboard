"""Composição da experiência analítica Streamlit."""

import logging
from datetime import date
from typing import cast

import numpy as np
import pandas as pd
import streamlit as st

from core.bazin import B3_WEIGHTS
from core.portfolio import bootstrap, simulate_portfolios
from core.valuation import dividend_valuation, monthly_income
from data.demo import US_TICKERS, DemoProvider
from data.fetcher import CACHE, YahooBCBProvider
from data.models import DataError, MarketProvider
from services.analytics import Analysis, analyze
from ui import charts
from ui.components import methodology, metric_cards, number, summary_table

logger = logging.getLogger(__name__)


def valuation_tab() -> None:
    """Calculadoras herdadas da planilha, agora com premissas editáveis."""
    st.subheader("Valuation por dividendos")
    st.caption("Premissas hipotéticas por ação. Use uma única moeda para preço e dividendo.")
    c1, c2, c3, c4 = st.columns(4)
    dpa = c1.number_input("DPA anual assumido", min_value=0.0, value=2.0)
    target = c2.number_input("Yield exigido (%)", min_value=0.1, max_value=100.0, value=8.5)
    growth = c3.number_input("Crescimento perpétuo (%)", min_value=-50.0, max_value=50.0, value=3.0)
    discount = c4.number_input("Taxa de desconto (%)", min_value=0.1, max_value=100.0, value=10.0)
    try:
        dyt, ddm = dividend_valuation(dpa, target / 100, growth / 100, discount / 100)
        left, right = st.columns(2)
        left.metric("Preço por yield exigido", number(dyt), border=True)
        right.metric("Gordon · crescimento perpétuo", number(ddm), border=True)
    except ValueError as exc:
        st.warning(str(exc))
    st.caption(
        "Gordon pressupõe crescimento estável e desconto maior que crescimento. "
        "Os valores dependem integralmente das premissas informadas."
    )
    st.subheader("Renda mensal em moeda estrangeira")
    a, b, c, d = st.columns(4)
    capital = a.number_input("Capital para renda (BRL)", min_value=0.0, value=100_000.0)
    fx = b.number_input("Câmbio assumido (BRL/USD)", min_value=0.01, value=5.0)
    dy = c.number_input("Yield anual assumido (%)", min_value=0.0, max_value=100.0, value=6.0)
    tax = d.number_input("Hipótese de retenção (%)", min_value=0.0, max_value=100.0, value=0.0)
    income = monthly_income(capital, fx, dy / 100, tax / 100)
    st.metric("Renda mensal estimada após retenção", "USD " + number(income))
    st.caption(
        "Câmbio, yield e retenção são hipóteses editáveis. Custos de conversão e demais tributos "
        "não entram na estimativa; o modelo não representa uma apuração tributária."
    )


def results_tabs(result: Analysis, currency: str, contribution: float, rf: float) -> None:
    """Monta as visões de performance, risco e cenários."""
    primary = next(iter(result.strategies))
    st.caption(f"ESTRATÉGIA EM DESTAQUE · {primary}")
    primary_summary = cast(pd.Series, result.summary.loc[primary])
    metric_cards(primary_summary, currency)
    performance_tab, risk_tab, scenario_tab, value_tab, method_tab = st.tabs(
        ["Desempenho", "Risco & diversificação", "Cenários", "Valuation & renda", "Metodologia"]
    )
    with performance_tab:
        st.plotly_chart(charts.performance(result.strategies, currency), width="stretch")
        st.plotly_chart(charts.performance(result.strategies, currency, normalized=True), width="stretch")
        summary_table(result.summary)
        if result.radar is not None:
            st.subheader("Radar de preço · último fechamento")
            radar_table = result.radar.rename(
                columns={
                    "price": "Preço",
                    "dpa": "DPA ponderado",
                    "buy_ceiling": "Teto comprar",
                    "hold_ceiling": "Teto manter",
                    "signal": "Sinal",
                    "allocation": "Peso de novos recursos",
                }
            )
            st.dataframe(
                radar_table,
                width="stretch",
                column_config={"Peso de novos recursos": st.column_config.NumberColumn(format="percent")},
            )
            if result.radar["signal"].eq("SEM HISTÓRICO").any():
                st.info("Alguns ativos não têm cinco anos completos de proventos e ficaram sem sinal Bazin.")
    with risk_tab:
        st.plotly_chart(charts.drawdowns(result.strategies), width="stretch")
        left, right = st.columns(2)
        with left:
            st.plotly_chart(charts.correlation(result.asset_returns), width="stretch")
        with right:
            st.plotly_chart(
                charts.distribution(result.strategies[primary]["return"], float(primary_summary["var"])),
                width="stretch",
            )
        st.caption("VaR/CVaR: perda mensal histórica a 95%. Correlação não implica proteção em crises.")
    with scenario_tab:
        if len(result.strategies[primary]["return"].dropna()) < 12:
            st.info("Cenários exigem pelo menos 12 retornos mensais.")
        else:
            years = st.slider("Horizonte de cenários (anos)", 1, 20, 10, key="horizon")
            last_wealth = float(primary_summary["wealth"])
            paths = bootstrap(
                result.strategies[primary]["return"], last_wealth, contribution, months=years * 12
            )
            st.plotly_chart(charts.fan(paths, currency), width="stretch")
            for column, q, label in zip(
                st.columns(3), [0.05, 0.5, 0.95], ["Percentil 5", "Mediana", "Percentil 95"], strict=True
            ):
                column.metric(label, currency + " " + number(float(np.quantile(paths[:, -1], q))))
            cloud = simulate_portfolios(result.asset_returns, rf)
            st.plotly_chart(charts.portfolio_cloud(cloud), width="stretch")
            st.caption(
                "Alocações aleatórias sem venda a descoberto. Nuvem amostral, com média e "
                "covariância históricas. A seleção da melhor amostra é retrospectiva."
            )
    with value_tab:
        valuation_tab()
    with method_tab:
        methodology()


def render_dashboard() -> None:
    """Carrega um caso de uso e apresenta falhas de dados sem tracebacks na tela."""
    st.set_page_config(page_title="Invest Analytics | Risco & Retorno", page_icon="◈", layout="wide")
    st.markdown(
        """<style>
        .block-container {padding-top: 4rem; max-width: 1600px;}
        h1 {letter-spacing: -0.04em;}
        [data-testid="stMetricValue"] {font-size: 1.4rem;}
        @media (max-width: 1400px) {[data-testid="stMetricValue"] {font-size: 1.1rem;}}
        .st-key-portfolio_metrics [data-testid="stHorizontalBlock"] {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 0.75rem;
        }
        .st-key-portfolio_metrics [data-testid="stColumn"] {width: 100% !important; min-width: 0 !important;}
        [data-testid="stSidebar"] {border-right: 1px solid #23334c;}
    </style>""",
        unsafe_allow_html=True,
    )
    st.caption("INVEST ANALYTICS / RESEARCH WORKSPACE")
    st.title("Transforme dados em decisões.")
    st.write("Explore o retorno, entenda as perdas e compare estratégias com as mesmas regras.")
    st.sidebar.title("Configurar análise")
    source = st.sidebar.selectbox(
        "Fonte", ["Demonstração (sem internet)", "Mercado (Yahoo + BCB)"], key="source"
    )
    market = st.sidebar.selectbox("Mercado / moeda", ["B3 · BRL", "EUA · USD"], key="market")
    market_code = "B3" if market.startswith("B3") else "EUA"
    demo = source.startswith("Demonstração")
    universe = tuple(B3_WEIGHTS) if market_code == "B3" else US_TICKERS
    default_assets = list(universe[:5])
    if st.session_state.get("active_market") != market_code:
        st.session_state["tickers"] = default_assets
        st.session_state["active_market"] = market_code
    last_month = pd.Timestamp.now(tz="America/Sao_Paulo").date().replace(day=1) - pd.Timedelta(days=1)
    with st.sidebar.form("analysis_settings"):
        tickers = st.multiselect("Ativos", universe, key="tickers")
        start = st.date_input("Primeiro fechamento", value=date(2016, 1, 31), key="start")
        end = st.date_input("Última data", value=date(2025, 12, 31) if demo else last_month, key="end")
        capital = st.number_input(
            "Capital inicial", min_value=0.0, value=100_000.0, step=5_000.0, key="capital"
        )
        contribution = st.number_input(
            "Aporte mensal", min_value=0.0, value=1_000.0, step=100.0, key="contribution"
        )
        reinvest = st.checkbox("Reinvestir proventos", value=True, key="reinvest")
        use_weights = st.checkbox("Pesos do legado B3", value=True, key="legacy_weights")
        buy = st.number_input("Yield de compra (%)", min_value=0.1, max_value=99.0, value=8.5, key="buy")
        hold = st.number_input("Yield de manter (%)", min_value=0.1, max_value=99.0, value=6.0, key="hold")
        annual_rf = st.number_input(
            "Taxa livre de risco USD (% a.a.)", min_value=0.0, max_value=100.0, value=3.0, key="risk_free"
        )
        st.form_submit_button("Analisar carteira", type="primary", width="stretch")
    if st.sidebar.button("Atualizar dados de mercado", width="stretch"):
        CACHE.clear()
    st.sidebar.caption("Dados mensais · aportes no fim do mês · posições fracionárias")
    if not tickers:
        st.warning("Selecione ao menos um ativo para iniciar a análise.")
        return
    if start >= end:
        st.warning("A data inicial deve anteceder a data final.")
        return
    if capital + contribution <= 0:
        st.warning("Informe capital inicial ou aporte maior que zero.")
        return
    if market_code == "B3" and hold >= buy:
        st.warning("O yield de manter deve ser menor que o yield de compra.")
        return
    provider: MarketProvider = DemoProvider() if demo else YahooBCBProvider()
    history_start = f"{max(2010, start.year - 5) if demo else start.year - 5}-01-01"
    try:
        with st.spinner("Preparando séries e calculando indicadores…"):
            data = provider.load(tuple(tickers), history_start, end.isoformat(), market_code)
            result = analyze(
                data,
                start.replace(day=1).isoformat(),
                capital,
                contribution,
                market_code,
                buy / 100,
                hold / 100,
                reinvest,
                annual_rf / 100,
                use_weights,
            )
    except (DataError, ValueError, KeyError, OSError) as exc:
        logger.exception("analysis_failed")
        st.error(f"Não foi possível concluir a análise: {exc}")
        st.info("Revise datas e ativos, atualize os dados ou selecione Demonstração.")
        return
    if demo:
        st.info("DEMONSTRAÇÃO · Dados sintéticos de 2010–2025 para explorar a ferramenta.")
    window = next(iter(result.strategies.values())).index
    st.caption(
        f"{data.source} · {data.currency} · {window[0]:%m/%Y} a {window[-1]:%m/%Y} "
        f"· {len(window) - 1} intervalos mensais"
    )
    for note in data.notes:
        st.caption(note)
    if len(window) < 37:
        st.warning("Janela menor que 36 retornos: métricas e caudas têm baixa precisão estatística.")
    # A nuvem usa uma referência anual efetiva, com a conversão explícita do CDI.
    rf = annual_rf / 100
    if market_code == "B3":
        rf = (
            float(cast(float, (1 + data.cash_returns.reindex(window[1:])).prod())) ** (12 / (len(window) - 1))
            - 1
        )
    results_tabs(result, data.currency, contribution, rf)
    st.caption(
        "Ferramenta de pesquisa e apoio à decisão. Resultados históricos e cenários não garantem retorno futuro."
    )
