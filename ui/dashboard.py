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
from ui.components import executive_summary, methodology, metric_cards, number, summary_table
from ui.theme import chips, hero

logger = logging.getLogger(__name__)

SIGNAL_COLORS = {
    "COMPRAR": "green",
    "MANTER": "orange",
    "AGUARDAR": "red",
    "SEM HISTÓRICO": "gray",
    "SEM DIVIDENDOS": "gray",
    "SEM PREÇO": "gray",
}
DEFAULT_US_TICKERS = ("O", "CVX", "ED", "ADM", "XOM", "JNJ", "PEP", "KO", "PG", "ABT")
PRESENTATION: dict[str, object] = {
    "source": "Demonstração (sem internet)",
    "market": "B3 · BRL",
    "active_market": "B3",
    "tickers": list(B3_WEIGHTS),
    "start": date(2016, 1, 31),
    "end": date(2025, 12, 31),
    "capital": 100_000.0,
    "contribution": 1_000.0,
    "reinvest": True,
    "legacy_weights": True,
    "buy": 8.5,
    "hold": 6.0,
    "risk_free": 3.0,
}


def load_presentation() -> None:
    """Restaura parâmetros estáveis e offline para demonstrações ao vivo."""
    st.session_state.update(PRESENTATION)


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
    st.latex(r"P_{yield} = \frac{D}{y} \qquad P_{Gordon} = \frac{D\,(1+g)}{k-g}, \quad k > g")
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
    st.metric("Renda mensal estimada após retenção", "USD " + number(income), border=True)
    st.caption(
        "Câmbio, yield e retenção são hipóteses editáveis. Custos de conversão e demais tributos "
        "não entram na estimativa; o modelo não representa uma apuração tributária."
    )


def radar_section(radar: pd.DataFrame) -> None:
    """Tabela do Radar com sinais coloridos por situação."""
    st.subheader("Radar de preço · último fechamento")
    radar_table = radar.rename(
        index=lambda t: str(t).replace(".SA", ""),
        columns={
            "price": "Preço",
            "dpa": "DPA ponderado",
            "buy_ceiling": "Teto comprar",
            "hold_ceiling": "Teto manter",
            "signal": "Sinal",
            "allocation": "Peso de novos recursos",
        },
    )
    for column in ["Preço", "DPA ponderado", "Teto comprar", "Teto manter"]:
        radar_table[column] = radar_table[column].map(lambda v: number(None if pd.isna(v) else float(v)))
    radar_table["Sinal"] = radar_table["Sinal"].map(lambda s: [s])
    radar_table.index.name = "Ticker"
    st.dataframe(
        radar_table,
        width="stretch",
        column_config={
            "Sinal": st.column_config.MultiselectColumn(
                options=list(SIGNAL_COLORS), color=list(SIGNAL_COLORS.values())
            ),
            "Peso de novos recursos": st.column_config.ProgressColumn(
                format="percent", min_value=0.0, max_value=1.0
            ),
        },
    )
    if radar["signal"].eq("SEM HISTÓRICO").any():
        st.info("Alguns ativos não têm cinco anos completos de proventos e ficaram sem sinal Bazin.")


def performance_subtitle(summary: pd.DataFrame, primary: str, benchmark: str) -> str | None:
    """Título-conclusão: diferença de patrimônio final contra o índice."""
    if benchmark not in summary.index or benchmark == primary:
        return None
    mine, other = (
        float(cast(float, summary.loc[primary, "wealth"])),
        float(cast(float, summary.loc[benchmark, "wealth"])),
    )
    if not (np.isfinite(mine) and np.isfinite(other)) or other <= 0:
        return None
    gap = mine / other - 1
    side = "acima" if gap >= 0 else "abaixo"
    return f"{primary} terminou {number(abs(gap), True)} {side} de {benchmark} com os mesmos aportes"


def results_tabs(
    result: Analysis,
    currency: str,
    contribution: float,
    rf: float,
    benchmark: str = "",
    real_data: bool = False,
) -> None:
    """Monta as visões de performance, risco e cenários."""
    primary = next(iter(result.strategies))
    primary_summary = cast(pd.Series, result.summary.loc[primary])
    reference = (
        cast(pd.Series, result.summary.loc[benchmark])
        if benchmark in result.summary.index and benchmark != primary
        else None
    )
    executive_summary(result.summary, primary, benchmark, currency, result.strategies[primary].index)
    st.caption(
        f"ESTRATÉGIA EM DESTAQUE · {primary}"
        + (f" · setas = diferença em relação a {benchmark}" if reference is not None else "")
    )
    metric_cards(primary_summary, currency, reference, benchmark)
    performance_tab, risk_tab, scenario_tab, value_tab, method_tab = st.tabs(
        ["📈 Desempenho", "🛡️ Risco & diversificação", "🔮 Cenários", "💰 Valuation & renda", "📐 Metodologia"]
    )
    with performance_tab:
        st.plotly_chart(
            charts.performance(
                result.strategies,
                currency,
                subtitle=performance_subtitle(result.summary, primary, benchmark),
                show_events=real_data,
            ),
            width="stretch",
        )
        st.plotly_chart(
            charts.performance(result.strategies, currency, normalized=True, show_events=real_data),
            width="stretch",
        )
        summary_table(result.summary)
        if result.radar is not None:
            radar_section(result.radar)
    with risk_tab:
        st.plotly_chart(charts.drawdowns(result.strategies, show_events=real_data), width="stretch")
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
                column.metric(
                    label, currency + " " + number(float(np.quantile(paths[:, -1], q))), border=True
                )
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
    hero(
        "INVEST ANALYTICS / RESEARCH WORKSPACE",
        "Transforme dados em decisões.",
        "Explore o retorno, entenda as perdas e compare estratégias com as mesmas regras.",
    )
    st.sidebar.title("Configurar análise")
    source = st.sidebar.selectbox(
        "Fonte",
        ["Demonstração (sem internet)", "Mercado (Yahoo + BCB)"],
        key="source",
        persist_state="session",
    )
    market = st.sidebar.selectbox(
        "Mercado / moeda", ["B3 · BRL", "EUA · USD"], key="market", persist_state="session"
    )
    market_code = "B3" if market.startswith("B3") else "EUA"
    demo = source.startswith("Demonstração")
    universe = tuple(B3_WEIGHTS) if market_code == "B3" else US_TICKERS
    default_assets = list(B3_WEIGHTS) if market_code == "B3" else list(DEFAULT_US_TICKERS)
    if st.session_state.get("active_market") != market_code:
        st.session_state["tickers"] = default_assets
        st.session_state["active_market"] = market_code
    last_month = pd.Timestamp.now(tz="America/Sao_Paulo").date().replace(day=1) - pd.Timedelta(days=1)
    with st.sidebar.form("analysis_settings"):
        tickers = st.multiselect("Ativos", universe, key="tickers", persist_state="session")
        period_start, period_end = st.columns(2)
        start = period_start.date_input(
            "Início", value=date(2016, 1, 31), key="start", persist_state="session"
        )
        end = period_end.date_input(
            "Fim",
            value=date(2025, 12, 31) if demo else last_month,
            key="end",
            persist_state="session",
        )
        capital = st.number_input(
            "Capital inicial",
            min_value=0.0,
            value=100_000.0,
            step=5_000.0,
            key="capital",
            persist_state="session",
        )
        contribution = st.number_input(
            "Aporte mensal",
            min_value=0.0,
            value=1_000.0,
            step=100.0,
            key="contribution",
            persist_state="session",
        )
        reinvest = st.checkbox("Reinvestir proventos", value=True, key="reinvest", persist_state="session")
        with st.expander("Parâmetros avançados"):
            use_weights = st.checkbox(
                "Pesos do legado B3", value=True, key="legacy_weights", persist_state="session"
            )
            buy = st.number_input(
                "Yield de compra (%)",
                min_value=0.1,
                max_value=99.0,
                value=8.5,
                key="buy",
                persist_state="session",
            )
            hold = st.number_input(
                "Yield de manter (%)",
                min_value=0.1,
                max_value=99.0,
                value=6.0,
                key="hold",
                persist_state="session",
            )
            annual_rf = st.number_input(
                "Taxa livre de risco USD (% a.a.)",
                min_value=0.0,
                max_value=100.0,
                value=3.0,
                key="risk_free",
                persist_state="session",
            )
        st.form_submit_button("Analisar carteira", type="primary", width="stretch")
    if st.sidebar.button("Atualizar dados de mercado", width="stretch"):
        CACHE.clear()
    st.sidebar.button(
        "Cenário da apresentação",
        width="stretch",
        on_click=load_presentation,
        help="Volta aos parâmetros padrão em modo demonstração, sem depender de internet.",
    )
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
    window = next(iter(result.strategies.values())).index
    chips(
        [
            data.currency,
            f"{window[0]:%m/%Y} a {window[-1]:%m/%Y}",
            f"{len(window) - 1} intervalos mensais",
            f"{len(tickers)} ativos",
        ],
        demo=demo,
    )
    st.caption(" · ".join([f"Fonte: {data.source} · {data.currency}", *data.notes]))
    if len(window) < 37:
        st.warning("Janela menor que 36 retornos: métricas e caudas têm baixa precisão estatística.")
    # A nuvem usa uma referência anual efetiva, com a conversão explícita do CDI.
    rf = annual_rf / 100
    if market_code == "B3":
        rf = (
            float(cast(float, (1 + data.cash_returns.reindex(window[1:])).prod())) ** (12 / (len(window) - 1))
            - 1
        )
    results_tabs(result, data.currency, contribution, rf, data.benchmark_name, real_data=not demo)
    st.caption(
        "Ferramenta de pesquisa e apoio à decisão. Resultados históricos e cenários não garantem retorno futuro."
    )
