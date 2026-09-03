from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from math import isfinite

from .enterprise_core import Initiative, InitiativeStatus, OperatingDecision


class ReallocationAction(str, Enum):
    INVEST = "INVEST"
    MAINTAIN = "MAINTAIN"
    REDUCE = "REDUCE"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class InitiativeResult:
    """Observed result used to update portfolio allocation without executing it."""

    initiative_id: str
    actual_value: float
    actual_cost: float
    actual_effort: float
    success: bool = True
    risk_event: bool = False

    def __post_init__(self) -> None:
        if not self.initiative_id:
            raise ValueError("initiative_id is required")
        for value in (self.actual_value, self.actual_cost, self.actual_effort):
            if not isfinite(value) or value < 0:
                raise ValueError("Observed result values must be finite and non-negative")


@dataclass(frozen=True)
class InitiativePerformance:
    initiative_id: str
    value_ratio: float
    cost_ratio: float
    effort_ratio: float
    forecast_error: float
    health: str


@dataclass(frozen=True)
class Reallocation:
    initiative_id: str
    action: ReallocationAction
    score: float
    rationale: str


@dataclass(frozen=True)
class ReallocationPlan:
    objective: str
    reallocations: tuple[Reallocation, ...]
    selected_ids: tuple[str, ...]
    reduced_ids: tuple[str, ...]
    stopped_ids: tuple[str, ...]
    escalated_ids: tuple[str, ...]
    bottlenecks: tuple[str, ...]
    warnings: tuple[str, ...]
    capacity_used: float
    budget_used: float


class DynamicPortfolioEngine:
    """Re-evaluate the whole portfolio from evidence and reallocate scarce resources.

    This is a recommendation engine only. It cannot authorize, spend, execute, or
    mutate governance. Portfolio selection is solved globally for the supplied
    bounded candidate set rather than by a greedy ranking.
    """

    @staticmethod
    def evaluate(initiative: Initiative, result: InitiativeResult) -> InitiativePerformance:
        if initiative.id != result.initiative_id:
            raise ValueError("Result does not belong to initiative")
        expected_value = max(abs(initiative.expected_value), 1e-9)
        expected_cost = max(initiative.cost, 1e-9)
        expected_effort = max(initiative.effort, 1e-9)
        value_ratio = result.actual_value / expected_value
        cost_ratio = result.actual_cost / expected_cost
        effort_ratio = result.actual_effort / expected_effort
        forecast_error = abs(value_ratio - 1.0)
        if result.risk_event or not result.success:
            health = "DANGEROUS"
        elif value_ratio >= 1.15 and cost_ratio <= 1.10 and effort_ratio <= 1.10:
            health = "OUTPERFORMING"
        elif value_ratio >= 0.85 and cost_ratio <= 1.25 and effort_ratio <= 1.25:
            health = "ON_TRACK"
        else:
            health = "UNDERPERFORMING"
        return InitiativePerformance(
            initiative.id,
            round(value_ratio, 6),
            round(cost_ratio, 6),
            round(effort_ratio, 6),
            round(forecast_error, 6),
            health,
        )

    @staticmethod
    def _score(initiative: Initiative, performance: InitiativePerformance | None) -> float:
        base = initiative.operating_score
        if performance is None:
            return base
        if performance.health == "DANGEROUS":
            return -abs(base)
        if performance.health == "OUTPERFORMING":
            return base * min(1.5, 1.0 + 0.5 * performance.value_ratio)
        if performance.health == "UNDERPERFORMING":
            return base * min(0.75, performance.value_ratio)
        return base

    @classmethod
    def rebalance(
        cls,
        objective: str,
        initiatives: tuple[Initiative, ...],
        *,
        results: tuple[InitiativeResult, ...] = (),
        current_active_ids: tuple[str, ...] = (),
        capacity_budget: float,
        financial_budget: float,
        max_active: int = 3,
    ) -> ReallocationPlan:
        if not objective:
            raise ValueError("Operating objective is required")
        if capacity_budget < 0 or financial_budget < 0:
            raise ValueError("Operating budgets cannot be negative")
        if max_active < 1:
            raise ValueError("max_active must be positive")

        by_id = {initiative.id: initiative for initiative in initiatives}
        if len(by_id) != len(initiatives):
            raise ValueError("initiative ids must be unique")
        result_by_id = {result.initiative_id: result for result in results}
        if len(result_by_id) != len(results):
            raise ValueError("result initiative ids must be unique")
        unknown_results = sorted(set(result_by_id) - set(by_id))
        if unknown_results:
            raise ValueError("Results reference unknown initiatives: " + ", ".join(unknown_results))
        unknown_active = sorted(set(current_active_ids) - set(by_id))
        if unknown_active:
            raise ValueError("Current portfolio references unknown initiatives: " + ", ".join(unknown_active))

        performances = {
            initiative.id: cls.evaluate(initiative, result_by_id[initiative.id])
            for initiative in initiatives
            if initiative.id in result_by_id
        }
        warnings: list[str] = []
        bottlenecks: list[str] = []

        for initiative in initiatives:
            performance = performances.get(initiative.id)
            if performance and performance.effort_ratio > 1.25:
                bottlenecks.append(f"EFFORT:{initiative.id}")
            if performance and performance.cost_ratio > 1.25:
                bottlenecks.append(f"BUDGET:{initiative.id}")

        candidates = tuple(
            initiative
            for initiative in initiatives
            if initiative.status not in {
                InitiativeStatus.COMPLETED,
                InitiativeStatus.DROPPED,
                InitiativeStatus.BLOCKED,
            }
            and cls._score(initiative, performances.get(initiative.id)) > 0
        )

        best_value = 0.0
        best: tuple[Initiative, ...] = ()
        limit = min(max_active, len(candidates))
        for size in range(1, limit + 1):
            for combo in combinations(candidates, size):
                cost = sum(item.cost for item in combo)
                effort = sum(item.effort for item in combo)
                if cost > financial_budget or effort > capacity_budget:
                    continue
                value = sum(cls._score(item, performances.get(item.id)) for item in combo)
                ids = tuple(sorted(item.id for item in combo))
                best_ids = tuple(sorted(item.id for item in best))
                if value > best_value or (value == best_value and ids < best_ids):
                    best_value, best = value, combo

        selected_ids = {item.id for item in best}
        reduced: list[str] = []
        stopped: list[str] = []
        escalated: list[str] = []
        allocations: list[Reallocation] = []

        for initiative in sorted(initiatives, key=lambda item: item.id):
            performance = performances.get(initiative.id)
            score = cls._score(initiative, performance)
            if initiative.status is InitiativeStatus.BLOCKED:
                allocations.append(Reallocation(initiative.id, ReallocationAction.ESCALATE, score, "Initiative is blocked and requires resolution before allocation"))
                escalated.append(initiative.id)
                continue
            if performance and performance.health == "DANGEROUS":
                allocations.append(Reallocation(initiative.id, ReallocationAction.STOP, score, "Observed failure or risk event requires containment"))
                stopped.append(initiative.id)
                continue
            if initiative.id in selected_ids:
                action = ReallocationAction.INVEST if initiative.id not in current_active_ids else ReallocationAction.MAINTAIN
                rationale = "Global portfolio optimum after incorporating observed results"
                if performance and performance.health == "OUTPERFORMING":
                    rationale += "; outperforming evidence supports additional allocation"
                allocations.append(Reallocation(initiative.id, action, score, rationale))
            elif initiative.id in current_active_ids:
                allocations.append(Reallocation(initiative.id, ReallocationAction.REDUCE, score, "Resources should be reallocated to higher-value feasible initiatives"))
                reduced.append(initiative.id)
            else:
                allocations.append(Reallocation(initiative.id, ReallocationAction.REDUCE, score, "Not selected by the constrained global portfolio optimization"))

        if not best:
            warnings.append("NO_POSITIVE_FEASIBLE_PORTFOLIO")
        if len(current_active_ids) > max_active:
            warnings.append("CURRENT_PORTFOLIO_OVER_CAPACITY")
        if bottlenecks:
            warnings.append("RESOURCE_BOTTLENECKS_DETECTED")

        return ReallocationPlan(
            objective=objective,
            reallocations=tuple(allocations),
            selected_ids=tuple(sorted(selected_ids)),
            reduced_ids=tuple(sorted(set(reduced))),
            stopped_ids=tuple(sorted(set(stopped))),
            escalated_ids=tuple(sorted(set(escalated))),
            bottlenecks=tuple(sorted(set(bottlenecks))),
            warnings=tuple(dict.fromkeys(warnings)),
            capacity_used=round(sum(item.effort for item in best), 4),
            budget_used=round(sum(item.cost for item in best), 4),
        )
