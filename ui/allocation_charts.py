"""Comparações visuais do plano de aporte B3."""

import plotly.graph_objects as go

from core.allocation import AllocationResult
from ui.charts import PALETTE, style


def allocation_comparison(result: AllocationResult) -> go.Figure:
    """Pesos por ativo antes/depois, incluindo caixa no total final."""
    orders = result.orders
    labels = [str(t).replace(".SA", "") for t in orders.index] + ["Caixa novo"]
    cash_weight = result.residual_cash / result.final_value
    figure = go.Figure()
    for name, values, color in [
        ("Antes", [*orders["current_weight"], 0.0], PALETTE[1]),
        ("Após aporte", [*orders["final_weight"], cash_weight], PALETTE[0]),
        ("Meta", [*orders["target_weight"], 0.0], PALETTE[2]),
    ]:
        figure.add_trace(
            go.Bar(
                x=labels,
                y=values,
                name=name,
                marker_color=color,
                hovertemplate="%{x}: %{y:.2%}<extra>%{fullData.name}</extra>",
            )
        )
    figure.update_layout(barmode="group", separators=",.")
    figure.update_yaxes(tickformat=".0%")
    return style(figure, "Carteira antes × depois × meta", "Participação no patrimônio")


def contribution_breakdown(result: AllocationResult) -> go.Figure:
    """Mostra o destino do dinheiro novo, com o resíduo explicitamente separado."""
    amounts = result.orders["allocated"]
    labels = [str(t).replace(".SA", "") for t in amounts.index] + ["Caixa residual"]
    figure = go.Figure(
        go.Bar(
            x=labels,
            y=[*amounts, result.residual_cash],
            marker_color=[PALETTE[0]] * len(amounts) + [PALETTE[2]],
            hovertemplate="%{x}: R$ %{y:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(separators=",.")
    return style(figure, "Distribuição do novo aporte", "Reais (R$)")
