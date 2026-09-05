from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class InitiativeStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"


class OperatingDecision(str, Enum):
    INVEST = "INVEST"
    MAINTAIN = "MAINTAIN"
    REDUCE = "REDUCE"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class KPI:
    """A measurable operating signal with explicit target and current value."""

    name: str
    current: float
    target: float
    weight: float = 1.0
    higher_is_better: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("KPI name is required")
        for value in (self.current, self.target, self.weight):
            if not isfinite(value):
                raise ValueError("KPI values must be finite")
        if self.weight < 0:
            raise ValueError("KPI weight must be non-negative")

    @property
    def attainment(self) -> float:
        if self.target == 0:
            return 1.0 if self.current == 0 else 0.0
        ratio = self.current / self.target if self.higher_is_better else self.target / self.current
        return max(0.0, min(1.5, ratio))

    @property
    def gap(self) -> float:
        return self.target - self.current if self.higher_is_better else self.current - self.target


@dataclass(frozen=True)
class Initiative:
    """A bounded company initiative competing for scarce resources."""

    id: str
    name: str
    objective: str
    owner: str
    expected_value: float
    probability: float
    cost: float
    effort: float
    urgency: float = 5.0
    strategic_fit: float = 5.0
    ownership_gain: float = 0.0
    recurring_gain: float = 0.0
    reversibility: float = 5.0
    risk: float = 5.0
    status: InitiativeStatus = InitiativeStatus.PROPOSED

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.objective or not self.owner:
            raise ValueError("Initiatives require id, name, objective and owner")
        for value in (
            self.expected_value,
            self.probability,
            self.cost,
            self.effort,
            self.urgency,
            self.strategic_fit,
            self.ownership_gain,
            self.recurring_gain,
            self.reversibility,
            self.risk,
        ):
            if not isfinite(value):
                raise ValueError("Initiative values must be finite")
        if not 0 <= self.probability <= 1:
            raise ValueError("Probability must be in [0, 1]")
        if min(self.cost, self.effort) < 0:
            raise ValueError("Cost and effort cannot be negative")

    @property
    def expected_net_value(self) -> float:
        return self.expected_value * self.probability - self.cost

    @property
    def operating_score(self) -> float:
        """Risk-adjusted value per unit of scarce effort, with ownership/recurrence leverage."""
        risk_factor = max(0.05, 1.0 - self.risk / 12.0)
        leverage = 1.0 + max(0.0, self.ownership_gain) + max(0.0, self.recurring_gain)
        strategic = max(0.0, min(10.0, self.strategic_fit)) / 10.0
        urgency = max(0.0, min(10.0, self.urgency)) / 10.0
        effort_factor = max(self.effort, 0.25)
        return (self.expected_net_value * risk_factor * leverage * (0.7 + 0.3 * strategic) * (0.8 + 0.2 * urgency)) / effort_factor


@dataclass(frozen=True)
class OperatingAllocation:
    initiative_id: str
    decision: OperatingDecision
    score: float
    rationale: str


@dataclass(frozen=True)
class OperatingPlan:
    objective: str
    allocations: tuple[OperatingAllocation, ...]
    selected_ids: tuple[str, ...]
    blocked_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    capacity_used: float
    budget_used: float

    @property
    def has_positive_engine(self) -> bool:
        return any(a.decision is OperatingDecision.INVEST and a.score > 0 for a in self.allocations)


class EnterpriseOperatingCore:
    """SINGULAR's company-level resource allocation and operating cadence.

    It coordinates scarce resources across initiatives. It does not authorize
    external actions, spend money, or change governance; those remain separate
    control boundaries.
    """

    @staticmethod
    def prioritize(
        objective: str,
        initiatives: tuple[Initiative, ...],
        *,
        capacity_budget: float,
        financial_budget: float,
        max_active: int = 3,
        kpis: tuple[KPI, ...] = (),
    ) -> OperatingPlan:
        if not objective:
            raise ValueError("Operating objective is required")
        if capacity_budget < 0 or financial_budget < 0:
            raise ValueError("Operating budgets cannot be negative")
        if max_active < 1:
            raise ValueError("max_active must be positive")

        warnings: list[str] = []
        if not initiatives:
            return OperatingPlan(objective, (), (), (), ("NO_INITIATIVES",), 0.0, 0.0)

        if kpis:
            weighted_attainment = sum(k.attainment * k.weight for k in kpis)
            weight_total = sum(k.weight for k in kpis)
            if weight_total and weighted_attainment / weight_total < 0.8:
                warnings.append("KPI_PORTFOLIO_BELOW_TARGET")

        ranked = sorted(initiatives, key=lambda i: (-i.operating_score, i.id))
        selected: list[Initiative] = []
        capacity_used = 0.0
        budget_used = 0.0

        for initiative in ranked:
            if initiative.status in {InitiativeStatus.COMPLETED, InitiativeStatus.DROPPED, InitiativeStatus.BLOCKED}:
                continue
            if initiative.expected_net_value <= 0:
                continue
            if len(selected) >= max_active:
                break
            if capacity_used + initiative.effort > capacity_budget:
                continue
            if budget_used + initiative.cost > financial_budget:
                continue
            selected.append(initiative)
            capacity_used += initiative.effort
            budget_used += initiative.cost

        selected_ids = tuple(i.id for i in selected)
        allocations = tuple(
            OperatingAllocation(
                initiative_id=i.id,
                decision=OperatingDecision.INVEST if i.id in selected_ids else OperatingDecision.REDUCE,
                score=i.operating_score,
                rationale=(
                    "Selected for highest risk-adjusted value within capacity/budget limits"
                    if i.id in selected_ids
                    else "Not selected after constrained portfolio ranking"
                ),
            )
            for i in ranked
            if i.status not in {InitiativeStatus.COMPLETED, InitiativeStatus.DROPPED}
        )
        blocked_ids = tuple(
            i.id for i in initiatives if i.status is InitiativeStatus.BLOCKED
        )
        if not selected:
            warnings.append("NO_POSITIVE_FEASIBLE_INITIATIVE")

        return OperatingPlan(
            objective=objective,
            allocations=allocations,
            selected_ids=selected_ids,
            blocked_ids=blocked_ids,
            warnings=tuple(dict.fromkeys(warnings)),
            capacity_used=capacity_used,
            budget_used=budget_used,
        )
