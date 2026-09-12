from __future__ import annotations

"""Explicit boundary between the legacy Opportunity model and the canonical World Model.

The adapter is intentionally one-way: decision engines may consume a normalized
Opportunity view, while the epistemically typed World Model remains the source of
truth. This prevents a second opportunity registry from silently becoming canonical.
"""

from .models import Opportunity
from .world_model import WorldOpportunity


class OpportunityAdapter:
    """Convert canonical WorldOpportunity records into the decision-engine schema."""

    @staticmethod
    def to_decision_model(opportunity_id: str, opportunity: WorldOpportunity) -> Opportunity:
        if not opportunity_id.strip():
            raise ValueError("opportunity_id cannot be empty")

        # World Model uses normalized potential/probability/reversibility in [0, 1].
        # The legacy decision model uses [0, 10] for impact/leverage/risk/reversibility.
        # Cost/time/risk are preserved as normalized effort signals and clamped to the
        # legacy scale so the adapter cannot create invalid downstream models.
        risk = min(10.0, opportunity.risk)
        cost = min(10.0, opportunity.cost)
        leverage = min(10.0, opportunity.leverage_score * 10.0)

        return Opportunity(
            id=opportunity_id,
            name=opportunity.name,
            impact=opportunity.potential * 10.0,
            probability=opportunity.probability,
            leverage=leverage,
            cost=cost,
            risk=risk,
            reversibility=opportunity.reversibility * 10.0,
            optionality=min(10.0, (1.0 + len(opportunity.synergies)) * 2.0),
        )

    @classmethod
    def world_model_opportunities(cls, opportunities: dict[str, WorldOpportunity]) -> list[Opportunity]:
        return [
            cls.to_decision_model(opportunity_id, opportunity)
            for opportunity_id, opportunity in sorted(opportunities.items())
        ]
