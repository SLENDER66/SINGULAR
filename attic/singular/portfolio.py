from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .models import Opportunity
from .opportunity_adapter import OpportunityAdapter
from .opportunity_engine import OpportunityAssessment, OpportunityDecision, OpportunityEngine
from .world_model import WorldModel


@dataclass(frozen=True)
class PortfolioSelection:
    opportunity_id: str
    allocation: float
    assessment: OpportunityAssessment


@dataclass(frozen=True)
class PortfolioAssessment:
    selections: tuple[PortfolioSelection, ...]
    total_cost: float
    total_risk: float
    expected_value: float
    rejected_ids: tuple[str, ...]


class PortfolioEngine:
    """Allocate scarce resources across opportunities instead of ranking them independently.

    The engine recommends a portfolio only; it does not authorize spending or execution.
    WorldModel is the canonical source for world opportunities; ``optimize_world``
    crosses the explicit adapter boundary before invoking the legacy optimizer.
    """

    @staticmethod
    def _utility(assessment: OpportunityAssessment, opportunity: Opportunity) -> float:
        # Expected upside adjusted by the opportunity engine's asymmetry score.
        return (
            opportunity.impact
            * opportunity.probability
            * (1 + opportunity.leverage / 10)
            * (1 + opportunity.optionality / 10)
            / (1 + opportunity.risk)
        )

    @classmethod
    def optimize(
        cls,
        opportunities: list[Opportunity],
        *,
        budget: float,
        risk_budget: float,
        max_positions: int | None = None,
    ) -> PortfolioAssessment:
        if budget < 0 or risk_budget < 0:
            raise ValueError("budget and risk_budget must be non-negative")
        if max_positions is not None and max_positions < 0:
            raise ValueError("max_positions must be non-negative")

        assessments = {item.id: OpportunityEngine.assess(item) for item in opportunities}
        candidates = [
            item
            for item in opportunities
            if assessments[item.id].decision in {OpportunityDecision.WATCH, OpportunityDecision.TEST}
        ]
        limit = len(candidates) if max_positions is None else min(max_positions, len(candidates))

        best: tuple[float, tuple[Opportunity, ...]] = (0.0, ())
        for size in range(1, limit + 1):
            for combo in combinations(candidates, size):
                total_cost = sum(item.cost for item in combo)
                total_risk = sum(item.risk * item.probability for item in combo)
                if total_cost > budget or total_risk > risk_budget:
                    continue
                value = sum(cls._utility(assessments[item.id], item) for item in combo)
                tie_break = tuple(sorted(item.id for item in combo))
                best_tie = tuple(sorted(item.id for item in best[1]))
                if value > best[0] or (value == best[0] and tie_break < best_tie):
                    best = (value, combo)

        selected_ids = {item.id for item in best[1]}
        selections = tuple(
            PortfolioSelection(item.id, item.cost, assessments[item.id])
            for item in sorted(
                best[1],
                key=lambda candidate: (-cls._utility(assessments[candidate.id], candidate), candidate.id),
            )
        )
        return PortfolioAssessment(
            selections=selections,
            total_cost=round(sum(item.cost for item in best[1]), 4),
            total_risk=round(sum(item.risk * item.probability for item in best[1]), 4),
            expected_value=round(best[0], 4),
            rejected_ids=tuple(sorted({item.id for item in opportunities if item.id not in selected_ids})),
        )

    @classmethod
    def optimize_world(
        cls,
        world_model: WorldModel,
        *,
        budget: float,
        risk_budget: float,
        max_positions: int | None = None,
    ) -> PortfolioAssessment:
        """Optimize opportunities held by the canonical epistemic World Model."""
        opportunities = OpportunityAdapter.world_model_opportunities(world_model.opportunities)
        return cls.optimize(
            opportunities,
            budget=budget,
            risk_budget=risk_budget,
            max_positions=max_positions,
        )
