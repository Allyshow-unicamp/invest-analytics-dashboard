"""Apresentação de indicadores e tabelas em português."""

import math

import pandas as pd
import streamlit as st


def number(value: float | None, percent: bool = False) -> str:
    """Formata valores ausentes sem exibir NaN/inf ao usuário."""
    if value is None or not math.isfinite(value):
        return "—"
    text = f"{value * 100 if percent else value:,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + ("%" if percent else "")


def metric_cards(row: pd.Series, currency: str) -> None:
    """Destaca valor da carteira e métricas de risco/retorno."""
    labels = [
        ("Patrimônio · " + currency, number(row["wealth"])),
        ("CAGR", number(row.get("cagr"), True)),
        ("Volatilidade a.a.", number(row.get("volatility"), True)),
        ("Sharpe anual", number(row.get("sharpe"))),
        ("Drawdown máximo", number(row.get("max_drawdown"), True)),
    ]
    with st.container(key="portfolio_metrics"):
        for column, (label, value) in zip(st.columns(len(labels)), labels, strict=True):
            column.metric(label, value, border=True)


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


def methodology() -> None:
    """Explicita hipóteses que alteram a interpretação dos resultados."""
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
  O benchmark nos EUA é SPY com proventos incorporados.
- O bootstrap sorteia meses independentes com reposição. Não prevê crises novas,
  dependência temporal ou mudanças de regime. As bandas são cenários empíricos.
- A cesta atual aplicada ao passado tem viés de sobrevivência. O estudo não
  demonstra capacidade preditiva, causalidade ou superioridade futura.
""")
