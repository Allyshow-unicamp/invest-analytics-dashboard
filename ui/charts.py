"""Figuras interativas reutilizáveis; todos os valores monetários na mesma moeda."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from numpy.typing import NDArray

from core.metrics import drawdown

PALETTE = ["#38d6bd", "#70aaff", "#eebc68", "#bb9af7", "#fb809b"]


def style(figure: go.Figure, title: str, y_title: str = "") -> go.Figure:
    """Aplica uma linguagem visual consistente aos painéis."""
    figure.update_layout(
        title=title,
        template="plotly_dark",
        colorway=PALETTE,
        height=390,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=15, r=20, t=65, b=25),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.2),
        yaxis_title=y_title,
        font=dict(family="Arial", color="#dce4ef"),
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(160,180,210,0.12)")
    return figure


def performance(strategies: dict[str, pd.DataFrame], currency: str, normalized: bool = False) -> go.Figure:
    """Compara patrimônio ou retorno acumulado sem fluxos externos."""
    figure = go.Figure()
    for name, frame in strategies.items():
        values = (1 + frame["return"].fillna(0)).cumprod() - 1 if normalized else frame["wealth"]
        figure.add_trace(go.Scatter(x=frame.index, y=values, name=name, line=dict(width=2.5)))
    if normalized:
        figure.update_yaxes(tickformat=".0%")
    return style(
        figure,
        "Retorno acumulado · livre de aportes" if normalized else "Evolução do patrimônio",
        "Retorno" if normalized else currency,
    )


def drawdowns(strategies: dict[str, pd.DataFrame]) -> go.Figure:
    """Mostra quedas da cota, evitando o efeito artificial dos aportes."""
    figure = go.Figure()
    for name, frame in strategies.items():
        r = frame["return"].dropna()
        if not r.empty:
            series = drawdown(r)
            figure.add_trace(go.Scatter(x=series.index, y=series, name=name, fill="tozeroy"))
    figure.update_yaxes(tickformat=".0%")
    return style(figure, "Drawdown da cota", "Queda desde o pico")


def correlation(returns: pd.DataFrame) -> go.Figure:
    """Matriz de correlação calculada somente na janela comum dos ativos."""
    figure = px.imshow(
        returns.corr(),
        zmin=-1,
        zmax=1,
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale=["#fb809b", "#1b263b", "#38d6bd"],
    )
    return style(figure, "Correlação dos retornos totais mensais")


def distribution(returns: pd.Series, var: float) -> go.Figure:
    """Histograma mensal com a perda VaR histórica de 95%."""
    figure = go.Figure(go.Histogram(x=returns.dropna(), nbinsx=35, marker_color=PALETTE[0], name="Retornos"))
    figure.add_vline(x=-var, line_color=PALETTE[4], line_dash="dash", annotation_text="VaR 95%")
    figure.update_xaxes(tickformat=".0%")
    return style(figure, "Distribuição de retornos mensais", "Meses")


def portfolio_cloud(portfolios: pd.DataFrame) -> go.Figure:
    """Nuvem amostral; a legenda não promete uma fronteira otimizada."""
    figure = px.scatter(
        portfolios,
        x="volatility",
        y="expected_return",
        color="score",
        color_continuous_scale="Teal",
        labels={
            "volatility": "Volatilidade anual",
            "expected_return": "Retorno esperado anual",
            "score": "Excesso / vol.",
        },
    )
    figure.update_traces(marker=dict(size=5, opacity=0.6))
    figure.update_xaxes(tickformat=".0%")
    figure.update_yaxes(tickformat=".0%")
    return style(figure, "Risco × retorno · carteiras simuladas", "Média aritmética anualizada")


def fan(paths: NDArray[np.float64], currency: str) -> go.Figure:
    """Bandas empíricas p5/p25/p50/p75/p95, incluindo instante zero."""
    quantiles = np.quantile(paths, [0.05, 0.25, 0.5, 0.75, 0.95], axis=0)
    figure = go.Figure()
    x = np.arange(paths.shape[1])
    for lower, upper, color, name in [
        (0, 4, "rgba(56,214,189,0.12)", "p5–p95"),
        (1, 3, "rgba(56,214,189,0.22)", "p25–p75"),
    ]:
        figure.add_trace(
            go.Scatter(x=x, y=quantiles[upper], line=dict(width=0), showlegend=False, hoverinfo="skip")
        )
        figure.add_trace(
            go.Scatter(
                x=x,
                y=quantiles[lower],
                fill="tonexty",
                fillcolor=color,
                line=dict(width=0),
                name=name,
                hoverinfo="skip",
            )
        )
    figure.add_trace(go.Scatter(x=x, y=quantiles[2], name="Mediana", line=dict(color=PALETTE[0], width=3)))
    figure.update_xaxes(title="Meses à frente")
    return style(figure, "Cenários de patrimônio · bootstrap histórico", currency)
