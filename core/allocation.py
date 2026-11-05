"""Aportes B3 sem vendas, com otimização contínua e execução em lotes inteiros."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import minimize

Vector = NDArray[np.float64]


class AllocationStrategy(StrEnum):
    """Estratégias disponíveis para investir apenas novos recursos."""

    REBALANCE = "rebalance"
    PROPORTIONAL = "proportional"
    MIN_VARIANCE = "min_variance"
    MAX_SHARPE = "max_sharpe"


@dataclass(frozen=True)
class Position:
    """Posição atual e meta por ativo; target_weight é uma fração entre 0 e 1."""

    ticker: str
    quantity: float
    average_price: float
    target_weight: float
    asset_class: str = "Ação"
    lot_size: int = 1


@dataclass(frozen=True)
class AllocationResult:
    """Plano indicativo, caixa e riscos calculados na mesma amostra histórica."""

    orders: pd.DataFrame
    contribution: float
    allocated: float
    residual_cash: float
    current_value: float
    final_value: float
    volatility_before: float | None
    volatility_after: float | None
    volatility_after_invested: float | None
    observations: int
    strategy: AllocationStrategy


def normalize_b3_ticker(ticker: str) -> str:
    """Normaliza códigos como ITUB4, ITUB4F e ITUB4.SA para a consulta Yahoo.

    O sufixo F identifica o livro fracionário; o provedor recebe o código-base.
    A validação é sintática e não comprova a existência/listagem do ativo.
    """
    symbol = ticker.strip().upper()
    if symbol.endswith(".SA"):
        symbol = symbol[:-3]
    if symbol.endswith("F"):
        symbol = symbol[:-1]
    if not re.fullmatch(r"[A-Z][A-Z0-9]{3}[0-9]{1,2}", symbol):
        raise ValueError(f"Ticker B3 inválido: {ticker!r}. Exemplo: ITUB4, HGLG11 ou BOVA11.")
    return symbol + ".SA"


def _cents(value: float) -> int:
    """Converte valores financeiros a centavos com arredondamento comercial."""
    return int(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _simplex_projection(values: Vector, total: float) -> Vector:
    """Projeta um vetor no simplex x >= 0, sum(x) = total em O(n log n)."""
    ordered = np.sort(values)[::-1]
    thresholds = (np.cumsum(ordered) - total) / np.arange(1, len(ordered) + 1)
    active = np.flatnonzero(ordered > thresholds)
    threshold = thresholds[active[-1]]
    return cast(Vector, np.maximum(values - threshold, 0))


class RebalancingEngine:
    """Calcula sugestões de compra sem UI, rede ou estado global.

    Quantidades atuais e compras são inteiras. O dinheiro é contabilizado em
    centavos. O resíduo continua no denominador da carteira como caixa novo.
    Preço médio informa o custo, mas não altera o peso de mercado ou o sinal.
    """

    def __init__(
        self,
        positions: Sequence[Position],
        prices: Mapping[str, float],
        historical_returns: pd.DataFrame | None = None,
        periods_per_year: int = 252,
    ) -> None:
        if not positions:
            raise ValueError("Inclua pelo menos um ativo na carteira.")
        self.positions = tuple(replace(p, ticker=normalize_b3_ticker(p.ticker)) for p in positions)
        self.tickers = tuple(p.ticker for p in self.positions)
        if len(set(self.tickers)) != len(self.tickers):
            raise ValueError("Tickers duplicados após normalizar os códigos B3.")
        normalized_prices = {normalize_b3_ticker(t): p for t, p in prices.items()}
        if set(normalized_prices) != set(self.tickers):
            raise ValueError("Cotações devem cobrir exatamente os ativos informados.")
        for position in self.positions:
            numeric = (position.quantity, position.average_price, position.target_weight)
            if not np.isfinite(numeric).all() or min(numeric) < 0 or position.target_weight > 1:
                raise ValueError("Quantidades, preços médios e metas devem ser finitos e não negativos.")
            if not float(position.quantity).is_integer():
                raise ValueError("As quantidades atuais devem ser inteiras na B3.")
            if position.lot_size < 1 or int(position.lot_size) != position.lot_size:
                raise ValueError("O lote mínimo deve ser um inteiro positivo.")
        self.targets: Vector = np.array([p.target_weight for p in self.positions], dtype=float)
        if not np.isclose(self.targets.sum(), 1.0, rtol=0, atol=1e-8):
            raise ValueError("As alocações alvo devem somar 100%. Metas zeradas não recebem compras.")
        quotes = [normalized_prices[t] for t in self.tickers]
        if not np.isfinite(quotes).all() or min(quotes) <= 0:
            raise ValueError("Todas as cotações devem ser positivas e finitas.")
        self.price_cents = np.array([_cents(p) for p in quotes], dtype=np.int64)
        if (self.price_cents <= 0).any():
            raise ValueError("Cotação inferior ao centavo mínimo suportado.")
        self.quantities = np.array([int(p.quantity) for p in self.positions], dtype=np.int64)
        self.lots = np.array([int(p.lot_size) for p in self.positions], dtype=np.int64)
        self.current: Vector = self.price_cents.astype(float) * self.quantities
        if periods_per_year < 1:
            raise ValueError("A frequência de anualização deve ser positiva.")
        self.periods_per_year = periods_per_year
        self.returns = self._validate_returns(historical_returns)

    def _validate_returns(self, returns: pd.DataFrame | None) -> pd.DataFrame | None:
        if returns is None:
            return None
        if set(returns.columns) != set(self.tickers) or returns.columns.duplicated().any():
            raise ValueError("O histórico deve cobrir exatamente os ativos da carteira.")
        result = returns.loc[:, list(self.tickers)].astype(float)
        if not np.isfinite(result.to_numpy()).all() or (result < -1).any().any():
            raise ValueError("Retornos históricos contêm lacunas ou valores inválidos.")
        if not result.index.is_unique or not result.index.is_monotonic_increasing:
            raise ValueError("Datas históricas devem ser únicas e crescentes.")
        return result

    def allocate(
        self,
        contribution: float,
        strategy: AllocationStrategy = AllocationStrategy.REBALANCE,
        annual_risk_free: float = 0.0,
    ) -> AllocationResult:
        """Distribui o aporte, arredonda lotes e preserva orçamento e posições.

        Rebalanceamento minimiza o erro quadrático em relação às metas finais
        sem vendas. A otimização de risco considera a carteira consolidada,
        não apenas o dinheiro novo. Metas zero vedam novos recursos em todos
        os modos; nos modos de risco, metas positivas são elegibilidade, não
        limites de exposição. O plano discreto é uma aproximação heurística.
        """
        if not np.isfinite(contribution) or contribution < 0:
            raise ValueError("O aporte deve ser finito e não negativo.")
        if not np.isfinite(annual_risk_free) or annual_risk_free <= -1:
            raise ValueError("A taxa anual de referência deve ser finita e maior que -100%.")
        strategy = AllocationStrategy(strategy)
        budget = _cents(contribution)
        if budget + self.current.sum() <= 0:
            raise ValueError("Informe uma posição atual ou um aporte maior que zero.")
        eligible = self.targets > 0
        ideal = np.zeros(len(self.tickers), dtype=float)
        if budget:
            if strategy == AllocationStrategy.PROPORTIONAL:
                ideal = budget * self.targets
            elif strategy == AllocationStrategy.REBALANCE:
                deficits = self.targets * (self.current.sum() + budget) - self.current
                ideal[eligible] = _simplex_projection(deficits[eligible], float(budget))
            else:
                ideal = self._optimize(float(budget), strategy, annual_risk_free)
        bought = self._discretize(ideal, budget, eligible)
        spent_cents = bought * self.price_cents
        remaining_cents = budget - int(spent_cents.sum())
        if remaining_cents < 0 or (bought < 0).any():
            raise ArithmeticError("O plano calculado violou o orçamento.")
        final = self.current + spent_cents
        total = float(self.current.sum() + budget)
        final_weights = final / total
        current_weights = self.current / self.current.sum() if self.current.sum() else np.zeros(len(final))
        total_quantities = self.quantities + bought
        cost = np.array([p.quantity * p.average_price for p in self.positions]) + spent_cents / 100
        average_cost = np.divide(cost, total_quantities, out=np.zeros(len(final)), where=total_quantities > 0)
        orders = pd.DataFrame(
            {
                "ticker": self.tickers,
                "asset_class": [p.asset_class for p in self.positions],
                "price": self.price_cents / 100,
                "current_quantity": self.quantities,
                "current_value": self.current / 100,
                "current_weight": current_weights,
                "target_weight": self.targets,
                "ideal_allocation": ideal / 100,
                "buy_quantity": bought,
                "allocated": spent_cents / 100,
                "lot_size": self.lots,
                "final_quantity": total_quantities,
                "final_value": final / 100,
                "final_weight": final_weights,
                "average_price_after": average_cost,
                "target_gap": final_weights - self.targets,
            }
        ).set_index("ticker")
        before = self._volatility(current_weights) if self.current.sum() > 0 else None
        invested_weights = final / final.sum() if final.sum() else np.zeros(len(final))
        return AllocationResult(
            orders=orders,
            contribution=budget / 100,
            allocated=int(spent_cents.sum()) / 100,
            residual_cash=remaining_cents / 100,
            current_value=float(self.current.sum()) / 100,
            final_value=total / 100,
            volatility_before=before,
            volatility_after=self._volatility(final_weights),
            volatility_after_invested=self._volatility(invested_weights) if final.sum() else None,
            observations=len(self.returns) if self.returns is not None else 0,
            strategy=strategy,
        )

    def _discretize(self, ideal: Vector, budget: int, eligible: NDArray[np.bool_]) -> NDArray[np.int64]:
        """Arredonda para baixo e usa sobra somente se aproximar do plano contínuo.

        A melhoria gulosa é uma busca de vizinhança, não uma prova de ótimo
        inteiro. Como o ponto de partida é o piso, cada ativo recebe no máximo
        um lote adicional nesta etapa; o custo independe do tamanho do aporte.
        """
        lot_costs = self.price_cents * self.lots
        lot_counts = np.floor((ideal + 1e-8) / lot_costs).astype(np.int64)
        lot_counts[~eligible] = 0
        remaining = budget - int((lot_counts * lot_costs).sum())
        for _ in range(len(self.tickers)):
            distance = lot_counts * lot_costs - ideal
            improvement = -(2 * distance * lot_costs + lot_costs.astype(float) ** 2)
            valid = eligible & (lot_costs <= remaining) & (improvement > 1e-6)
            if not valid.any():
                break
            best = int(np.argmax(np.where(valid, improvement, -np.inf)))
            lot_counts[best] += 1
            remaining -= int(lot_costs[best])
        return lot_counts * self.lots

    def _optimize(self, budget: float, strategy: AllocationStrategy, annual_rf: float) -> Vector:
        if self.returns is None or len(self.returns) < 60:
            raise ValueError("A otimização exige ao menos 60 retornos diários completos por ativo.")
        covariance = self.returns.cov().to_numpy() * self.periods_per_year
        means = self.returns.mean().to_numpy() * self.periods_per_year
        if strategy == AllocationStrategy.MAX_SHARPE and np.max(np.abs(covariance)) < 1e-14:
            raise ValueError("Sharpe indefinido: o histórico não apresenta variância mensurável.")
        eligible = np.flatnonzero(self.targets > 0)
        total = float(self.current.sum() + budget)
        base = self.current / total
        scale = budget / total
        normalizer = max(float(np.max(np.diag(covariance))), 1e-12)
        annualized_rf = ((1 + annual_rf) ** (1 / self.periods_per_year) - 1) * self.periods_per_year

        def objective(new_weights: Vector) -> float:
            final_weights = base.copy()
            final_weights[eligible] += scale * new_weights
            variance = float(final_weights @ covariance @ final_weights)
            if strategy == AllocationStrategy.MIN_VARIANCE:
                return variance / normalizer
            excess = float(final_weights @ means) - annualized_rf
            return float(-excess / np.sqrt(max(variance, 1e-16)))

        starts = [self.targets[eligible] / self.targets[eligible].sum()]
        if strategy == AllocationStrategy.MAX_SHARPE:
            starts.extend(np.eye(len(eligible)))
        candidates: list[tuple[float, Vector]] = []
        for initial in starts:
            solution = minimize(
                objective,
                initial,
                method="SLSQP",
                bounds=[(0, 1)] * len(eligible),
                constraints=[{"type": "eq", "fun": lambda x: float(np.sum(x) - 1)}],
                options={"maxiter": 400, "ftol": 1e-11},
            )
            values = np.asarray(solution.x, dtype=float)
            if (
                solution.success
                and np.isfinite(values).all()
                and values.min() >= -1e-7
                and abs(float(values.sum()) - 1) <= 1e-6
            ):
                values = np.clip(values, 0, 1)
                values /= values.sum()
                candidates.append((objective(values), values))
        if not candidates:
            raise ValueError("O otimizador não convergiu para uma solução válida; tente outra estratégia.")
        _, best = min(candidates, key=lambda item: item[0])
        result = np.zeros(len(self.tickers), dtype=float)
        result[eligible] = best * budget
        return result

    def _volatility(self, weights: Vector) -> float | None:
        if self.returns is None or len(self.returns) < 60:
            return None
        covariance = self.returns.cov().to_numpy() * self.periods_per_year
        return float(np.sqrt(max(0, float(weights @ covariance @ weights))))
