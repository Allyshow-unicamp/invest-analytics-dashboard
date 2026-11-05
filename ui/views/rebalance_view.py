"""Simulador de aportes B3 com formulário, ordens indicativas e impacto de risco."""

import logging
from typing import cast

import numpy as np
import pandas as pd
import streamlit as st

from core.allocation import AllocationStrategy
from core.bazin import B3_WEIGHTS
from data.b3_market import B3Provider, YahooB3Provider
from data.models import DataError
from services.allocation import ContributionAnalysis, parse_positions, simulate_contribution
from ui.allocation_charts import allocation_comparison, contribution_breakdown
from ui.components import number
from ui.theme import hero

logger = logging.getLogger(__name__)
STRATEGIES = {
    "Rebalanceamento inteligente": AllocationStrategy.REBALANCE,
    "Alocação proporcional direta": AllocationStrategy.PROPORTIONAL,
    "Otimização de risco e retorno": AllocationStrategy.MIN_VARIANCE,
}


def _normalized_percents(tickers: list[str]) -> list[float]:
    """Converte pesos Bazin dos ativos selecionados em percentuais que somam 100,0%."""
    raw = np.array([B3_WEIGHTS.get(f"{t}.SA", 1.0) for t in tickers], dtype=float)
    total = float(raw.sum())
    scaled = raw / total * 100.0 if total > 0 else np.full(len(tickers), 100.0 / len(tickers))
    basis = np.floor(scaled * 10).astype(int)
    remainder = 1000 - int(basis.sum())
    if remainder > 0:
        order = np.argsort(-(scaled * 10 - basis))
        for idx in order[:remainder]:
            basis[int(idx)] += 1
    return [int(v) / 10.0 for v in basis]


def radar_buy_portfolio(radar_frame: pd.DataFrame | None) -> pd.DataFrame | None:
    """Monta a carteira base a partir das ações marcadas como COMPRAR no Radar."""
    if radar_frame is None or radar_frame.empty or "signal" not in radar_frame.columns:
        return None
    buys = radar_frame.loc[radar_frame["signal"].eq("COMPRAR")]
    if buys.empty:
        return None
    tickers = [str(t).replace(".SA", "") for t in buys.index]
    prices = [round(float(p), 2) for p in buys["price"]]
    return pd.DataFrame(
        {
            "ticker": tickers,
            "asset_class": ["Ação"] * len(tickers),
            "quantity": [0] * len(tickers),
            "average_price": prices,
            "target_percent": _normalized_percents(tickers),
            "lot_size": [1] * len(tickers),
        }
    )


def initial_portfolio(radar_frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """Usa as ações COMPRAR do último Radar Bazin ou o exemplo padrão se indisponível."""
    source = radar_frame if radar_frame is not None else st.session_state.get("latest_radar")
    if isinstance(source, pd.DataFrame):
        from_radar = radar_buy_portfolio(source)
        if from_radar is not None:
            return from_radar
    return pd.DataFrame(
        {
            "ticker": ["BBAS3", "TAEE11"],
            "asset_class": ["Ação", "Ação"],
            "quantity": [0, 0],
            "average_price": [27.0, 35.0],
            "target_percent": [50.0, 50.0],
            "lot_size": [1, 1],
        }
    )


def show_result(analysis: ContributionAnalysis) -> None:
    """Apresenta o plano e a composição; não transmite ordens a corretoras."""
    result, market = analysis.result, analysis.market
    st.caption(f"{market.source} · plano da última simulação enviada")
    for note in market.notes:
        st.warning(note)
    with st.container(horizontal=True):
        st.metric("Aporte disponível", "R$ " + number(result.contribution), border=True)
        st.metric("Total em compras", "R$ " + number(result.allocated), border=True)
        st.metric("Caixa residual", "R$ " + number(result.residual_cash), border=True)
    st.caption(
        "Patrimônio consolidado: R$ "
        + number(result.final_value)
        + ". O caixa residual permanece no denominador dos pesos finais."
    )
    if result.allocated == 0:
        st.info(
            "Nenhuma compra atende ao orçamento, lotes e distribuição calculada. O aporte permanece em caixa."
        )
    st.subheader("Ordens de compra sugeridas")
    orders = result.orders
    table = pd.DataFrame(index=orders.index)
    table["Preço atual"] = orders["price"].map(lambda x: "R$ " + number(x))
    table["Cotas a comprar"] = orders["buy_quantity"]
    table["Total alocado"] = orders["allocated"].map(lambda x: "R$ " + number(x))
    table["Peso resultante"] = orders["final_weight"].map(lambda x: number(x, True))
    table["Meta"] = orders["target_weight"].map(lambda x: number(x, True))
    table["Situação"] = [
        ["Comprar"] if q > 0 else ["Meta zero"] if t == 0 else ["Aguardar"]
        for q, t in zip(orders["buy_quantity"], orders["target_weight"], strict=True)
    ]
    table.index.name = "Ticker"
    st.dataframe(
        table,
        width="stretch",
        column_config={
            "Situação": st.column_config.MultiselectColumn(
                options=["Comprar", "Aguardar", "Meta zero"], color=["green", "orange", "gray"]
            ),
        },
    )
    st.caption(
        "Compras em unidades inteiras, conforme o lote mínimo informado. Preços de referência "
        "podem ter atraso e diferir do livro fracionário e do preço efetivo de execução."
    )
    st.plotly_chart(allocation_comparison(result), width="stretch", key="allocation_comparison")
    st.plotly_chart(contribution_breakdown(result), width="stretch", key="allocation_breakdown")
    st.subheader("Impacto na volatilidade histórica")
    with st.container(horizontal=True):
        st.metric("Antes do aporte", number(result.volatility_before, True), border=True)
        change = None
        if result.volatility_before is not None and result.volatility_after is not None:
            change = number((result.volatility_after - result.volatility_before) * 100) + " p.p."
        st.metric(
            "Após aporte · com caixa",
            number(result.volatility_after, True),
            delta=change,
            delta_color="inverse",
            border=True,
        )
        st.metric("Após aporte · só ativos", number(result.volatility_after_invested, True), border=True)
    if result.observations < 60:
        st.info("Histórico insuficiente: o plano está disponível, mas o impacto no risco não é mensurável.")
    else:
        st.caption(
            f"{result.observations} retornos diários ajustados na mesma janela · anualização por √252. "
            "A redução com caixa pode refletir dinheiro ainda não investido. Carteira inicial vazia não tem risco anterior mensurável."
        )
    with st.expander("Cotações usadas e posição consolidada"):
        quote_table = pd.DataFrame(
            {
                "Ticker": [q.ticker for q in market.quotes],
                "Cotação": ["R$ " + number(q.price) for q in market.quotes],
                "Referência (São Paulo)": [q.as_of.strftime("%d/%m/%Y %H:%M %Z") for q in market.quotes],
                "Tipo": [q.kind for q in market.quotes],
            }
        )
        st.dataframe(quote_table, hide_index=True, width="stretch")
        details = orders[["asset_class", "current_quantity", "final_quantity", "average_price_after"]].copy()
        details["average_price_after"] = details["average_price_after"].map(lambda x: "R$ " + number(x))
        st.dataframe(
            details.rename(
                columns={
                    "asset_class": "Classe",
                    "current_quantity": "Cotas antes",
                    "final_quantity": "Cotas depois",
                    "average_price_after": "Preço médio após compra",
                }
            ),
            width="stretch",
        )


def render_rebalance_view() -> None:
    """Permite editar o portfólio e simular somente ao enviar o formulário."""
    hero(
        "INVEST ANALYTICS / APORTES B3",
        "Dê um destino ao próximo aporte.",
        "Baseado nas ações marcadas como COMPRAR no Radar de preço · último fechamento.",
    )
    latest_radar = st.session_state.get("latest_radar")
    radar_base = radar_buy_portfolio(latest_radar) if isinstance(latest_radar, pd.DataFrame) else None
    signature = (
        tuple(radar_base["ticker"].tolist())
        if radar_base is not None
        else ("NONE",)
        if isinstance(latest_radar, pd.DataFrame)
        else None
    )
    if signature is not None and st.session_state.get("allocation_radar_sig") != signature:
        st.session_state["allocation_radar_sig"] = signature
        if radar_base is not None and "allocation_saved_positions" not in st.session_state:
            st.session_state["allocation_editor_base"] = radar_base.copy()
            st.session_state.pop("allocation_editor", None)
    if "allocation_editor_base" not in st.session_state:
        st.session_state["allocation_editor_base"] = st.session_state.get(
            "allocation_saved_positions", initial_portfolio()
        ).copy()
    if radar_base is not None:
        tickers_txt = ", ".join(radar_base["ticker"].tolist())
        col_msg, col_btn = st.columns([4, 1])
        col_msg.caption(f"Sinais **COMPRAR** no último fechamento do Radar Bazin: **{tickers_txt}**.")
        if col_btn.button("Recarregar do Radar", width="stretch"):
            st.session_state["allocation_editor_base"] = radar_base.copy()
            st.session_state.pop("allocation_saved_positions", None)
            st.session_state.pop("allocation_editor", None)
            st.rerun()
    elif isinstance(latest_radar, pd.DataFrame):
        st.info(
            "Nenhum ativo teve sinal COMPRAR no último fechamento do Radar Bazin. "
            "Ajuste o yield de compra no dashboard ou edite os ativos manualmente abaixo."
        )
    with st.expander("Carteira, metas e regras do aporte", expanded=True), st.form("allocation_form"):
        portfolio = st.data_editor(
            st.session_state["allocation_editor_base"],
            key="allocation_editor",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "ticker": st.column_config.TextColumn(
                    "Ticker B3",
                    required=True,
                    help="Ex.: ITUB4, BBAS3, TAEE11. O sufixo .SA é adicionado automaticamente.",
                ),
                "asset_class": st.column_config.SelectboxColumn(
                    "Classe", options=["Ação", "FII", "ETF"], required=True, default="Ação"
                ),
                "quantity": st.column_config.NumberColumn(
                    "Cotas atuais", min_value=0, step=1, required=True, default=0
                ),
                "average_price": st.column_config.NumberColumn(
                    "Preço médio (R$)", min_value=0.0, step=0.01, format="R$ %.2f", required=True, default=0.0
                ),
                "target_percent": st.column_config.NumberColumn(
                    "Meta (%)", min_value=0.0, max_value=100.0, step=0.1, required=True, default=0.0
                ),
                "lot_size": st.column_config.NumberColumn(
                    "Lote mínimo", min_value=1, step=1, required=True, default=1
                ),
            },
        )
        st.caption(
            "Metas por ativo devem somar 100%. Use lote 1 para unidades no mercado fracionário; "
            "lotes maiores são configuráveis. Classes são informativas. Quantidades decimais não são aceitas."
        )
        contribution = st.number_input(
            "Valor do aporte (R$)",
            min_value=0.0,
            max_value=1_000_000_000.0,
            value=5_000.0,
            step=100.0,
            format="%.2f",
            key="allocation_amount",
            persist_state="session",
        )
        strategy_name = st.selectbox(
            "Estratégia de alocação", list(STRATEGIES), key="allocation_strategy", persist_state="session"
        )
        criterion = st.selectbox(
            "Critério da otimização de risco",
            ["Variância mínima", "Sharpe máximo"],
            key="allocation_criterion",
            help="Usado somente na estratégia de otimização.",
            persist_state="session",
        )
        years = st.selectbox(
            "Histórico para o risco (anos)",
            [1, 3, 5],
            index=1,
            key="allocation_years",
            persist_state="session",
        )
        annual_rf = st.number_input(
            "Taxa livre de risco assumida (% a.a.)",
            min_value=0.0,
            max_value=100.0,
            value=10.0,
            step=0.5,
            key="allocation_rf",
            help="Hipótese para o Sharpe; não é uma cotação atual do CDI.",
            persist_state="session",
        )
        fresh = st.checkbox(
            "Atualizar cotações ao simular", value=True, key="allocation_fresh", persist_state="session"
        )
        submitted = st.form_submit_button(
            "Simular aporte", type="primary", key="allocation_submit", width="stretch"
        )
    if submitted:
        st.session_state.pop("allocation_analysis", None)
        try:
            positions = parse_positions(cast(pd.DataFrame, portfolio))
            strategy = STRATEGIES[strategy_name]
            if strategy_name == "Otimização de risco e retorno" and criterion == "Sharpe máximo":
                strategy = AllocationStrategy.MAX_SHARPE
            provider: B3Provider = YahooB3Provider()
            with st.spinner("Consultando preços no Yahoo Finance e calculando compras…"):
                analysis = simulate_contribution(
                    positions, contribution, strategy, provider, years, annual_rf / 100, fresh
                )
            st.session_state["allocation_analysis"] = analysis
            st.session_state["allocation_saved_positions"] = portfolio.copy()
        except (ValueError, DataError, ArithmeticError, KeyError, OSError) as exc:
            logger.warning("contribution_analysis_failed: %s", type(exc).__name__)
            st.error(f"Não foi possível simular o aporte: {exc}")
    stored = st.session_state.get("allocation_analysis")
    if isinstance(stored, ContributionAnalysis):
        show_result(stored)
    elif not submitted:
        st.info(
            "Edite a carteira e clique em Simular aporte. Nenhuma consulta de mercado é feita antes do envio."
        )
    with st.expander("Como o plano é calculado"):
        st.markdown("""
- **Base do Radar Bazin:** a carteira inicial parte dos ativos com sinal **COMPRAR** na tabela *Radar de preço · último fechamento* do dashboard, ponderados pelos pesos do legado B3.
- **Rebalanceamento:** aproxima os pesos finais das metas, comprando os ativos com maior déficit. Posições existentes não são vendidas.
- **Proporcional:** aplica as metas diretamente ao dinheiro novo, independentemente dos desvios atuais.
- **Risco/retorno:** otimiza a carteira consolidada por variância mínima ou Sharpe. Metas positivas indicam ativos elegíveis; não são limites de exposição nesse modo.
- **Meta zero:** bloqueia compras, preservando qualquer posição já existente, inclusive na otimização.
- **Lotes:** o plano contínuo é arredondado para baixo. A sobra compra um lote adicional somente se aproximar a distribuição do plano calculado. Não há garantia de ótimo inteiro nem de aporte integralmente investido.
- **Preços e risco:** Yahoo pode ter atraso. Os horários são apresentados; o histórico ajustado exclui o pregão corrente. Custos, tributos, liquidez e slippage não entram na simulação.
- **Privacidade:** posições e resultados ficam na memória da sessão no servidor; não são gravados em arquivos ou enviados a corretoras. A fonte recebe somente tickers e janela de preços.
""")
