from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

class AllocationDecision(str, Enum):
    FUND = 'FUND'
    TEST = 'TEST'
    HOLD = 'HOLD'
    EXIT = 'EXIT'

@dataclass
class PortfolioItem:
    name: str
    category: str
    expected_value: float
    probability: float
    leverage: float
    cost: float
    risk: float
    optionality: float = 0.0
    strategic_fit: float = 0.0
    momentum: float = 0.0
    resource_need: float = 1.0
    status: str = 'PROPOSED'
    id: str = field(default_factory=lambda: 'PF-' + uuid4().hex[:10])

    @property
    def risk_adjusted_value(self) -> float:
        return round(self.expected_value * self.probability * (1 + self.leverage / 10) + self.optionality + self.strategic_fit + self.momentum - self.risk * 0.5, 3)

    @property
    def efficiency(self) -> float:
        return round(self.risk_adjusted_value / max(self.cost + self.resource_need, 0.1), 3)

    def classify(self, fund_threshold: float = 10.0, test_threshold: float = 3.0) -> AllocationDecision:
        if self.risk >= 8 and self.optionality < 3:
            return AllocationDecision.HOLD
        if self.efficiency >= fund_threshold:
            return AllocationDecision.FUND
        if self.efficiency >= test_threshold:
            return AllocationDecision.TEST
        if self.status in {'ACTIVE', 'IN_PROGRESS'} and self.momentum < 0:
            return AllocationDecision.EXIT
        return AllocationDecision.HOLD

@dataclass
class ResourceBudget:
    name: str
    capacity: float
    reserved: float = 0.0
    minimum_reserve: float = 0.0

    @property
    def available(self) -> float:
        return max(self.capacity - self.reserved - self.minimum_reserve, 0.0)

@dataclass
class Allocation:
    item_id: str
    item_name: str
    amount: float
    decision: AllocationDecision
    rationale: str

class PortfolioEngine:
    """Ranks initiatives and allocates scarce resources without executing external side effects."""
    def rank(self, items: list[PortfolioItem]) -> list[PortfolioItem]:
        return sorted(items, key=lambda x: (x.efficiency, x.risk_adjusted_value), reverse=True)

    def allocate(self, items: list[PortfolioItem], budgets: list[ResourceBudget]) -> list[Allocation]:
        ranked = self.rank(items)
        out: list[Allocation] = []
        for item in ranked:
            decision = item.classify()
            budget = next((b for b in budgets if b.name == item.category), None)
            if budget is None:
                out.append(Allocation(item.id, item.name, 0.0, AllocationDecision.HOLD, 'Aucun budget de catégorie.'))
                continue
            if decision in {AllocationDecision.FUND, AllocationDecision.TEST} and budget.available > 0:
                amount = min(item.resource_need, budget.available)
                budget.reserved += amount
                out.append(Allocation(item.id, item.name, round(amount, 3), decision, 'Allocation priorisée par valeur ajustée, efficacité et contraintes.'))
            else:
                out.append(Allocation(item.id, item.name, 0.0, decision, 'Conserver sans nouvelle allocation.'))
        return out

@dataclass
class CompoundingLoop:
    name: str
    drivers: tuple[str, ...]
    reinforcement: float
    durability: float
    scalability: float
    fragility: float = 0.0

    @property
    def score(self) -> float:
        return round(self.reinforcement * self.durability * self.scalability - self.fragility, 3)

class CompoundingEngine:
    def rank(self, loops: list[CompoundingLoop]) -> list[CompoundingLoop]:
        return sorted(loops, key=lambda x: x.score, reverse=True)

    def strongest(self, loops: list[CompoundingLoop]) -> CompoundingLoop | None:
        ranked = self.rank(loops)
        return ranked[0] if ranked else None

@dataclass
class RiskExposure:
    name: str
    probability: float
    impact: float
    concentration: float = 0.0
    detectability: float = 0.5

    @property
    def score(self) -> float:
        return round(self.probability * self.impact * (1 + self.concentration) * (1.5 - self.detectability), 3)

class RiskControlEngine:
    def rank(self, exposures: list[RiskExposure]) -> list[RiskExposure]:
        return sorted(exposures, key=lambda x: x.score, reverse=True)

    def concentration(self, exposures: list[RiskExposure]) -> float:
        if not exposures:
            return 0.0
        total = sum(max(x.impact, 0) for x in exposures)
        if total <= 0:
            return 0.0
        largest = max(x.impact * (1 + x.concentration) for x in exposures)
        return round(largest / total, 3)

@dataclass
class EmpireControlSnapshot:
    portfolio_value: float
    allocated_resources: float
    top_initiatives: list[str]
    top_compounding_loop: str | None
    highest_risks: list[str]
    concentration_risk: float
    human_interventions_estimate: int

class EmpireControl:
    """V2.1 control layer: decide where to place scarce attention/resources and what to protect."""
    def __init__(self):
        self.portfolio = PortfolioEngine()
        self.compounding = CompoundingEngine()
        self.risks = RiskControlEngine()

    def snapshot(self, items: list[PortfolioItem], loops: list[CompoundingLoop], risks: list[RiskExposure], allocations: list[Allocation] | None = None) -> EmpireControlSnapshot:
        ranked = self.portfolio.rank(items)
        allocated = sum(a.amount for a in (allocations or []))
        top_loop = self.compounding.strongest(loops)
        top_risks = [r.name for r in self.risks.rank(risks)[:3]]
        interventions = sum(1 for a in (allocations or []) if a.decision in {AllocationDecision.FUND, AllocationDecision.TEST} and a.amount == 0)
        return EmpireControlSnapshot(
            portfolio_value=round(sum(max(i.risk_adjusted_value, 0) for i in ranked), 3),
            allocated_resources=round(allocated, 3),
            top_initiatives=[i.name for i in ranked[:5]],
            top_compounding_loop=top_loop.name if top_loop else None,
            highest_risks=top_risks,
            concentration_risk=self.risks.concentration(risks),
            human_interventions_estimate=interventions,
        )
