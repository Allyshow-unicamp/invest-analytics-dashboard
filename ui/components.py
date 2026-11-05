"""Apresentação de indicadores e tabelas em português."""

import math
from html import escape
from typing import cast

import pandas as pd
import streamlit as st

HELP = {
    "wealth": "Valor final da carteira, incluindo capital inicial, aportes e proventos.",
    "cagr": "Crescimento anual composto da cota, sem o efeito dos aportes.",
    "volatility": "Desvio-padrão anualizado dos retornos mensais. Quanto menor, mais estável.",
    "sharpe": "Retorno excedente à taxa livre de risco por unidade de risco. Acima de 0 supera a referência.",
    "max_drawdown": "Maior queda da cota desde um pico anterior. Mede a pior perda vivida.",
}


def number(value: float | None, percent: bool = False) -> str:
    """Formata valores ausentes sem exibir NaN/inf ao usuário."""
    if value is None or not math.isfinite(value):
        return "—"
    text = f"{value * 100 if percent else value:,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + ("%" if percent else "")


def _value(row: pd.Series | None, key: str) -> float | None:
    """Lê uma métrica como float finito, ou None quando indisponível."""
    if row is None:
        return None
    raw: object = row.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _signed(value: float, suffix: str = "", percent: bool = False) -> str:
    """Diferença com sinal explícito, usada como delta do st.metric."""
    return ("+" if value > 0 else "") + number(value * 100 if percent else value) + suffix


def _delta(row: pd.Series, reference: pd.Series | None, key: str, name: str, mode: str) -> str | None:
    """Compara a estratégia em destaque com o benchmark de mercado."""
    mine, other = _value(row, key), _value(reference, key)
    if mine is None or other is None:
        return None
    if mode == "relative":
        return _signed(mine / other - 1, "%", percent=True) if other > 0 else None
    if mode == "pp":
        return _signed(mine - other, " p.p.", percent=True)
    return _signed(mine - other)


def metric_cards(
    row: pd.Series, currency: str, reference: pd.Series | None = None, reference_name: str = ""
) -> None:
    """Destaca valor da carteira e métricas de risco/retorno contra o benchmark."""
    cards = [
        ("Patrimônio · " + currency, number(_value(row, "wealth")), "wealth", "relative", "normal"),
        ("CAGR", number(_value(row, "cagr"), True), "cagr", "pp", "normal"),
        ("Volatilidade a.a.", number(_value(row, "volatility"), True), "volatility", "pp", "inverse"),
        ("Sharpe anual", number(_value(row, "sharpe")), "sharpe", "abs", "normal"),
        ("Drawdown máximo", number(_value(row, "max_drawdown"), True), "max_drawdown", "pp", "normal"),
    ]
    with st.container(key="portfolio_metrics"):
        for column, (label, value, key, mode, color) in zip(st.columns(len(cards)), cards, strict=True):
            column.metric(
                label,
                value,
                delta=_delta(row, reference, key, reference_name, mode) if reference is not None else None,
                delta_color=color,  # type: ignore[arg-type]
                help=HELP[key],
                border=True,
            )


def executive_summary(
    summary: pd.DataFrame,
    primary: str,
    benchmark: str,
    currency: str,
    window: pd.Index,
) -> None:
    """Transforma os números em uma conclusão legível em poucos segundos."""
    row = cast(pd.Series, summary.loc[primary])
    wealth, contributed = _value(row, "wealth"), _value(row, "contributed")
    period = f"{pd.Timestamp(window[0]):%m/%Y} a {pd.Timestamp(window[-1]):%m/%Y}"
    parts = [
        f"De {period}, investindo {currency} {escape(number(contributed))} no total, a estratégia "
        f"<b>{escape(primary)}</b> chegaria a <b>{currency} {escape(number(wealth))}</b>."
    ]
    if benchmark in summary.index and benchmark != primary:
        ref = cast(pd.Series, summary.loc[benchmark])
        cagr, ref_cagr = _value(row, "cagr"), _value(ref, "cagr")
        if cagr is not None and ref_cagr is not None:
            gap = (cagr - ref_cagr) * 100
            css, verb = ("ia-up", "acima") if gap >= 0 else ("ia-down", "abaixo")
            cdi_note = ""
            if "CDI" in summary.index:
                cdi_cagr = _value(cast(pd.Series, summary.loc["CDI"]), "cagr")
                if cdi_cagr is not None:
                    cdi_gap = (cagr - cdi_cagr) * 100
                    cdi_css, cdi_verb = ("ia-up", "acima") if cdi_gap >= 0 else ("ia-down", "abaixo")
                    cdi_note = (
                        f' e <span class="{cdi_css}">{number(abs(cdi_gap))} p.p. {cdi_verb}</span> '
                        f"do CDI ({number(cdi_cagr, True)} a.a.)"
                    )
            parts.append(
                f"O crescimento anual foi de <b>{number(cagr, True)}</b>, "
                f'<span class="{css}">{number(abs(gap))} p.p. {verb}</span> de {escape(benchmark)} '
                f"({number(ref_cagr, True)} a.a.){cdi_note}."
            )
        dd, ref_dd = _value(row, "max_drawdown"), _value(ref, "max_drawdown")
        if dd is not None and ref_dd is not None:
            css = "ia-up" if dd >= ref_dd else "ia-down"
            parts.append(
                f'A pior queda foi de <span class="{css}">{number(dd, True)}</span>, '
                f"contra {number(ref_dd, True)} do índice."
            )
    st.markdown(
        '<div class="ia-summary"><div class="ia-summary-title">Resumo executivo</div>'
        + " ".join(parts)
        + "</div>",
        unsafe_allow_html=True,
    )


def summary_table(summary: pd.DataFrame) -> None:
    """Compara estratégias com formatação pt-BR e nomes de negócio."""
    names = {
        "wealth": "Patrimônio",
        "contributed": "Total aportado",
        "total_return": "Retorno total",
        "cagr": "CAGR",
        "volatility": "Volatilidade a.a.",
        "sharpe": "Sharpe a.a.",
        "max_drawdown": "Drawdown máximo",
        "var": "VaR 95% / mês",
        "cvar": "CVaR 95% / mês",
    }
    table = summary.reindex(columns=list(names)).copy()
    for column in table:
        is_percent = column not in {"wealth", "contributed", "sharpe"}
        table[column] = table[column].map(lambda v, pct=is_percent: number(v, pct))
    table.index.name = "Estratégia"
    st.dataframe(table.rename(columns=names), width="stretch")


def formulas() -> None:
    """Exibe as fórmulas centrais do estudo com notação matemática."""
    st.markdown("#### Fórmulas utilizadas")
    left, right = st.columns(2)
    with left:
        st.caption("Crescimento anual composto (CAGR), com n retornos mensais")
        st.latex(r"\text{CAGR} = \Big(\prod_{t=1}^{n}(1+r_t)\Big)^{12/n} - 1")
        st.caption("Índice de Sharpe anualizado sobre retornos excedentes mensais")
        st.latex(r"\text{Sharpe} = \frac{\overline{r_t - r_{f,t}}}{\sigma(r_t - r_{f,t})}\,\sqrt{12}")
        st.caption("Drawdown da cota em relação ao maior valor anterior")
        st.latex(r"DD_t = \frac{W_t}{\max_{s \le t} W_s} - 1")
    with right:
        st.caption("VaR e CVaR históricos a 95% (perda mensal)")
        st.latex(
            r"\text{VaR}_{95} = -Q_{5\%}(r) \qquad \text{CVaR}_{95} = -\mathbb{E}\left[r \mid r \le Q_{5\%}\right]"
        )
        st.caption("Dividendo por ação ponderado (Radar Bazin), D₁ = ano mais antigo")
        st.latex(r"\text{DPA}_{pond} = \frac{\sum_{k=1}^{5} k \cdot D_k}{15}")
        st.caption("Preços-teto a partir dos yields de compra e de manutenção")
        st.latex(
            r"P_{compra} = \frac{\text{DPA}_{pond}}{y_{compra}} \qquad P_{manter} = \frac{\text{DPA}_{pond}}{y_{manter}}"
        )


def pipeline() -> None:
    """Diagrama do fluxo de dados, da coleta à apresentação."""
    st.markdown("#### Arquitetura da análise")
    st.graphviz_chart(
        """
        digraph {
            rankdir=LR; bgcolor="transparent";
            node [shape=box, style="rounded,filled", fillcolor="#131f31", color="#38d6bd",
                  fontcolor="#e4edf8", fontname="Helvetica", margin="0.25,0.12"];
            edge [color="#70aaff"];
            dados [label="Dados\\nYahoo Finance · BCB"];
            cache [label="Cache local\\ne validação"];
            motor [label="Backtest mensal\\naportes · proventos"];
            estr [label="Estratégias\\nRadar Bazin · DCA\\nÍndice · CDI"];
            metr [label="Métricas\\nCAGR · Sharpe\\nDrawdown · VaR"];
            ui [label="Dashboard\\ninterativo"];
            dados -> cache -> motor -> estr -> metr -> ui;
        }
        """,
        width="stretch",
    )


def methodology() -> None:
    """Explicita hipóteses que alteram a interpretação dos resultados."""
    formulas()
    pipeline()
    with st.expander("Hipóteses e limitações do estudo", expanded=True):
        st.markdown("""
**Como ler a análise**

- A posição inicial é montada no primeiro fechamento selecionado. Os aportes
  mensais entram no fim dos intervalos seguintes, igualmente em todas as estratégias.
- CAGR e drawdown usam retornos da cota, descontando o efeito de aportes.
  A primeira queda é medida contra o capital inicial.
- Sharpe usa a média e o desvio-padrão dos retornos excedentes mensais, com
  anualização por √12. O CDI é a referência na B3; nos EUA, a taxa USD informada.
- VaR e CVaR são perdas históricas mensais a 95%, sem hipótese de normalidade.
  Não são limites máximos de perda. Amostras curtas produzem estimativas instáveis.
- O Radar usa os cinco anos-calendário anteriores completos de proventos,
  com pesos 1 a 5. Meses sem informação impedem o sinal. O filtro afeta novos
  recursos e não vende posições antigas. O sinal e a compra usam o fechamento
  mensal: uma aproximação que não modela execução no próximo pregão.
- Preços usados nas posições não têm ajuste por dividendos. Proventos são
  creditados separadamente sobre posições do mês anterior, usando a data ex como
  aproximação. Correlação e simulação de alocações usam preços ajustados por proventos.
- Sem reinvestimento, os proventos ficam numa reserva de caixa. Caixa rende CDI
  na B3 e 0% em USD. Impostos, custos, slippage e restrições de lote não são modelados.
- O Ibovespa é um índice de retorno total. Comparações em BRL e USD são separadas.
  O benchmark nos EUA é o ETF VOO com proventos incorporados.
- O bootstrap sorteia meses independentes com reposição. Não prevê crises novas,
  dependência temporal ou mudanças de regime. As bandas são cenários empíricos.
- A cesta atual aplicada ao passado tem viés de sobrevivência. O estudo não
  demonstra capacidade preditiva, causalidade ou superioridade futura.
""")
