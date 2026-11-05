"""Figuras interativas reutilizáveis; todos os valores monetários na mesma moeda."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from numpy.typing import NDArray

from core.metrics import drawdown

PALETTE = ["#38d6bd", "#70aaff", "#eebc68", "#bb9af7", "#fb809b"]
FONT = "Source Sans, Source Sans Pro, sans-serif"
# Eventos de mercado reais; só são marcados quando os dados não são sintéticos.
MARKET_EVENTS = [("Covid-19", "2020-02-01", "2020-04-30")]


def style(figure: go.Figure, title: str, y_title: str = "", subtitle: str | None = None) -> go.Figure:
    """Aplica uma linguagem visual consistente aos painéis."""
    figure.update_layout(
        title=dict(
            text=title,
            subtitle=dict(text=subtitle or "", font=dict(size=13, color="#8fa3bf")),
            x=0,
            xanchor="left",
            y=0.97,
            yanchor="top",
            font=dict(size=18, color="#e4edf8"),
        ),
        template="plotly_dark",
        colorway=PALETTE,
        height=410,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=15, r=20, t=100 if subtitle else 85, b=30),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#131f31", bordercolor="#23334c", font=dict(family=FONT)),
        legend=dict(
            orientation="h",
            x=0,
            xanchor="left",
            y=1.0,
            yanchor="bottom",
            bgcolor="rgba(0,0,0,0)",
            itemwidth=40,
        ),
        yaxis_title=y_title,
        separators=",.",
        font=dict(family=FONT, color="#dce4ef", size=14),
    )
    figure.update_xaxes(showgrid=False, linecolor="#23334c")
    figure.update_yaxes(gridcolor="rgba(160,180,210,0.10)", zeroline=False)
    return figure


def mark_events(figure: go.Figure, index: pd.Index) -> None:
    """Sombreia crises históricas que caem dentro da janela analisada."""
    if index.empty:
        return
    first, last = pd.Timestamp(index[0]), pd.Timestamp(index[-1])
    for label, start, end in MARKET_EVENTS:
        if first <= pd.Timestamp(start) and pd.Timestamp(end) <= last:
            figure.add_vrect(
                x0=start,
                x1=end,
                fillcolor="rgba(251,128,155,0.10)",
                line_width=0,
                annotation_text=label,
                annotation_position="top left",
                annotation_font=dict(size=11, color="#fb809b"),
            )


def line_style(position: int) -> dict[str, object]:
    """Destaca a estratégia principal e atenua as referências."""
    color = PALETTE[position % len(PALETTE)]
    if position == 0:
        return dict(color=color, width=3.5)
    return dict(color=color, width=1.8, dash="dot" if position >= 2 else "solid")


def performance(
    strategies: dict[str, pd.DataFrame],
    currency: str,
    normalized: bool = False,
    subtitle: str | None = None,
    show_events: bool = False,
) -> go.Figure:
    """Compara patrimônio ou retorno acumulado sem fluxos externos."""
    figure = go.Figure()
    for position, (name, frame) in enumerate(strategies.items()):
        values = (1 + frame["return"].fillna(0)).cumprod() - 1 if normalized else frame["wealth"]
        figure.add_trace(
            go.Scatter(
                x=frame.index,
                y=values,
                name=name,
                line=line_style(position),
                opacity=1.0 if position == 0 else 0.8,
                hovertemplate=("%{y:.1%}" if normalized else currency + " %{y:,.0f}")
                + "<extra>"
                + name
                + "</extra>",
            )
        )
    if normalized:
        figure.update_yaxes(tickformat=".0%")
    if show_events and strategies:
        mark_events(figure, next(iter(strategies.values())).index)
    return style(
        figure,
        "Retorno acumulado · livre de aportes" if normalized else "Evolução do patrimônio",
        "Retorno" if normalized else currency,
        subtitle,
    )


def drawdowns(strategies: dict[str, pd.DataFrame], show_events: bool = False) -> go.Figure:
    """Mostra quedas da cota, evitando o efeito artificial dos aportes."""
    figure = go.Figure()
    worst: tuple[pd.Timestamp, float, str] | None = None
    for position, (name, frame) in enumerate(strategies.items()):
        r = frame["return"].dropna()
        if r.empty:
            continue
        series = drawdown(r)
        figure.add_trace(
            go.Scatter(
                x=series.index,
                y=series,
                name=name,
                line=line_style(position),
                fill="tozeroy" if position == 0 else None,
                fillcolor="rgba(56,214,189,0.15)" if position == 0 else None,
                hovertemplate="%{y:.1%}<extra>" + name + "</extra>",
            )
        )
        if position == 0:
            lowest = int(np.argmin(series.to_numpy()))
            worst = (pd.Timestamp(series.index[lowest]), float(series.iloc[lowest]), name)
    figure.update_yaxes(tickformat=".0%")
    if show_events and strategies:
        mark_events(figure, next(iter(strategies.values())).index)
    subtitle = None
    if worst is not None and worst[1] < 0:
        when, depth, name = worst
        figure.add_annotation(
            x=when,
            y=depth,
            text=f"Pior queda · {depth:.1%}".replace(".", ","),
            showarrow=True,
            arrowhead=2,
            arrowcolor=PALETTE[0],
            ax=40,
            ay=30,
            font=dict(color="#e4edf8"),
            bgcolor="#131f31",
            bordercolor=PALETTE[0],
        )
        subtitle = f"{name}: queda máxima de {depth:.1%} em {when:%m/%Y}".replace(".", ",")
    return style(figure, "Drawdown da cota", "Queda desde o pico", subtitle)


def correlation(returns: pd.DataFrame) -> go.Figure:
    """Matriz de correlação calculada somente na janela comum dos ativos."""
    matrix = returns.corr()
    matrix.index = [str(t).replace(".SA", "") for t in matrix.index]
    matrix.columns = [str(t).replace(".SA", "") for t in matrix.columns]
    figure = px.imshow(
        matrix,
        zmin=-1,
        zmax=1,
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale=["#fb809b", "#1b263b", "#38d6bd"],
    )
    figure.update_layout(hovermode="closest")
    return style(
        figure,
        "Correlação dos retornos totais mensais",
        subtitle="Quanto mais perto de 0, maior a diversificação",
    )


def distribution(returns: pd.Series, var: float) -> go.Figure:
    """Histograma mensal com a perda VaR histórica de 95%."""
    figure = go.Figure(
        go.Histogram(x=returns.dropna(), nbinsx=35, marker_color=PALETTE[0], opacity=0.85, name="Retornos")
    )
    figure.add_vline(x=-var, line_color=PALETTE[4], line_dash="dash", annotation_text="VaR 95%")
    figure.update_xaxes(tickformat=".0%")
    figure.update_layout(hovermode="closest", bargap=0.05)
    return style(
        figure,
        "Distribuição de retornos mensais",
        "Meses",
        subtitle="Cauda à esquerda da linha: 5% piores meses",
    )


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
    figure.update_layout(hovermode="closest")
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
