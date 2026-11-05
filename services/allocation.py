"""Caso de uso: validar carteira, obter preços e simular um novo aporte B3."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.allocation import (
    AllocationResult,
    AllocationStrategy,
    Position,
    RebalancingEngine,
    normalize_b3_ticker,
)
from data.b3_market import B3Provider, B3Snapshot


@dataclass(frozen=True)
class ContributionAnalysis:
    """Plano e evidências de mercado da simulação, isolados da interface."""

    result: AllocationResult
    market: B3Snapshot


def parse_positions(table: pd.DataFrame) -> tuple[Position, ...]:
    """Converte percentuais da tabela para frações e valida antes de acessar APIs."""
    required = {"ticker", "quantity", "average_price", "target_percent", "asset_class", "lot_size"}
    if table.empty or not required.issubset(table.columns) or len(table) > 30:
        raise ValueError(
            "Preencha de 1 a 30 posições com ticker, quantidade, preço médio, meta, classe e lote."
        )
    positions: list[Position] = []
    try:
        for row in table.to_dict(orient="records"):
            lot = float(row["lot_size"])
            if not np.isfinite(lot) or not lot.is_integer() or lot < 1:
                raise ValueError("O lote mínimo deve ser um inteiro positivo.")
            asset_class = str(row["asset_class"])
            if asset_class not in {"Ação", "FII", "ETF"}:
                raise ValueError("Informe a classe Ação, FII ou ETF em todas as linhas.")
            positions.append(
                Position(
                    ticker=normalize_b3_ticker(str(row["ticker"])),
                    quantity=float(row["quantity"]),
                    average_price=float(row["average_price"]),
                    target_weight=float(row["target_percent"]) / 100,
                    asset_class=asset_class,
                    lot_size=int(lot),
                )
            )
    except (TypeError, OverflowError) as exc:
        raise ValueError("Preencha os campos numéricos de todas as posições.") from exc
    # Reutiliza as invariantes de domínio antes de qualquer consulta externa.
    RebalancingEngine(positions, {p.ticker: 1.0 for p in positions})
    return tuple(positions)


def simulate_contribution(
    positions: tuple[Position, ...],
    contribution: float,
    strategy: AllocationStrategy,
    provider: B3Provider,
    years: int = 3,
    annual_risk_free: float = 0.10,
    fresh_quotes: bool = True,
) -> ContributionAnalysis:
    """Consulta a fonte escolhida e retorna compras não negativas e caixa residual."""
    # Chamar diretamente o serviço também deve validar entradas antes da rede.
    normalized = RebalancingEngine(positions, {p.ticker: 1.0 for p in positions}).positions
    if not np.isfinite(contribution) or contribution < 0:
        raise ValueError("O aporte deve ser finito e não negativo.")
    snapshot = provider.load(tuple(p.ticker for p in normalized), years, fresh_quotes)
    if len(snapshot.quotes) != len(normalized) or len({q.ticker for q in snapshot.quotes}) != len(normalized):
        raise ValueError("A fonte devolveu cotações incompletas ou duplicadas.")
    result = RebalancingEngine(
        normalized, {q.ticker: q.price for q in snapshot.quotes}, snapshot.returns
    ).allocate(contribution, strategy, annual_risk_free)
    return ContributionAnalysis(result, snapshot)
