from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

class OpportunityDecision(str, Enum):
    ACT = 'ACT'; TEST = 'TEST'; WATCH = 'WATCH'; IGNORE = 'IGNORE'

@dataclass
class CapitalPosition:
    cash: float = 0.0
    monthly_income: float = 0.0
    monthly_expenses: float = 0.0
    investable_capital: float = 0.0
    debt: float = 0.0

    @property
    def monthly_surplus(self) -> float:
        return self.monthly_income - self.monthly_expenses

    @property
    def runway_months(self) -> float | None:
        if self.monthly_expenses <= 0: return None
        return round(self.cash / self.monthly_expenses, 2)

@dataclass
class Opportunity:
    name: str
    impact: float
    probability: float
    leverage: float
    timing: float
    cost: float
    risk: float
    reversibility: float = 0.5
    decision: OpportunityDecision = OpportunityDecision.WATCH
    id: str = field(default_factory=lambda: 'OPP-' + uuid4().hex[:10])

    def score(self) -> float:
        benefit = self.impact * self.probability * self.leverage * max(self.timing, 0.1)
        drag = max(self.cost, 0.1) * max(self.risk, 0.1)
        return round(benefit / drag, 3)

    def classify(self, test_threshold: float = 8.0, act_threshold: float = 15.0) -> OpportunityDecision:
        s = self.score()
        if self.risk >= 8 and self.reversibility <= 0.3: self.decision = OpportunityDecision.WATCH
        elif s >= act_threshold: self.decision = OpportunityDecision.ACT
        elif s >= test_threshold: self.decision = OpportunityDecision.TEST
        elif s >= 3: self.decision = OpportunityDecision.WATCH
        else: self.decision = OpportunityDecision.IGNORE
        return self.decision

@dataclass
class RevenueExperiment:
    hypothesis: str
    setup_cost: float
    expected_monthly_revenue: float
    probability: float
    duration_days: int
    status: str = 'PROPOSED'

    @property
    def expected_value(self) -> float:
        return round(self.expected_monthly_revenue * self.probability - self.setup_cost, 2)

    def go_no_go(self, max_cost: float, min_expected_value: float = 0.0) -> str:
        if self.setup_cost > max_cost: return 'NO_GO'
        return 'GO' if self.expected_value >= min_expected_value else 'NO_GO'

@dataclass
class StrategicAsset:
    name: str
    capital_value: float = 0.0
    capability_value: float = 0.0
    network_value: float = 0.0
    reputation_value: float = 0.0
    optionality: float = 0.0

    @property
    def strategic_value(self) -> float:
        return round(self.capital_value + self.capability_value + self.network_value + self.reputation_value + self.optionality, 2)

class CapitalEngine:
    def __init__(self, position: CapitalPosition | None = None): self.position = position or CapitalPosition()
    def snapshot(self) -> dict[str, Any]:
        p = self.position
        return {'cash': p.cash, 'income': p.monthly_income, 'expenses': p.monthly_expenses,
                'surplus': p.monthly_surplus, 'runway_months': p.runway_months,
                'investable_capital': p.investable_capital, 'debt': p.debt}

class OpportunityEngine:
    def rank(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        for o in opportunities: o.classify()
        return sorted(opportunities, key=lambda o: o.score(), reverse=True)

class RevenueEngine:
    def prioritize(self, experiments: list[RevenueExperiment]) -> list[RevenueExperiment]:
        return sorted(experiments, key=lambda x: x.expected_value, reverse=True)

class EmpireEngine:
    """Economic/strategic layer. It ranks opportunities and experiments; it does not move money or sign contracts."""
    def __init__(self, capital: CapitalEngine | None = None):
        self.capital = capital or CapitalEngine()
        self.opportunities = OpportunityEngine()
        self.revenue = RevenueEngine()
        self.assets: list[StrategicAsset] = []

    def strategic_snapshot(self) -> dict[str, Any]:
        return {
            'capital': self.capital.snapshot(),
            'assets': sorted([{'name': a.name, 'strategic_value': a.strategic_value} for a in self.assets], key=lambda x: x['strategic_value'], reverse=True),
        }
