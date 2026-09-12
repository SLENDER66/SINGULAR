from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Opportunity


class OpportunityDecision(str, Enum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    TEST = "TEST"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class OpportunityAssessment:
    opportunity_id: str
    score: float
    decision: OpportunityDecision
    reasons: tuple[str, ...]
    red_team_required: bool
    human_review_required: bool


class OpportunityEngine:
    """Detect asymmetric opportunities without treating outliers as automatic wins."""

    @staticmethod
    def score(opportunity: Opportunity) -> float:
        return round(
            opportunity.impact
            * opportunity.probability
            * (1 + opportunity.leverage / 10)
            * (1 + opportunity.optionality / 10)
            * (0.7 + opportunity.reversibility / 10)
            / (1 + opportunity.cost + opportunity.risk * 0.7),
            4,
        )

    @classmethod
    def assess(cls, opportunity: Opportunity) -> OpportunityAssessment:
        score = cls.score(opportunity)
        reasons: list[str] = []
        outlier_signals = 0

        if opportunity.leverage >= 8:
            reasons.append("FORT_LEVERAGE")
            outlier_signals += 1
        if opportunity.optionality >= 8:
            reasons.append("FORTE_OPTIONALITE")
            outlier_signals += 1
        if opportunity.cost <= 2:
            reasons.append("FAIBLE_COUT_INITIAL")
            outlier_signals += 1
        if opportunity.reversibility >= 8:
            reasons.append("FORTE_REVERSIBILITE")
            outlier_signals += 1
        if opportunity.impact >= 8 and opportunity.probability >= 0.5:
            reasons.append("UPSIDE_CREDIBLE")
            outlier_signals += 1
        if opportunity.risk >= 7:
            reasons.append("RISQUE_ELEVE")

        red_team_required = outlier_signals >= 3 or opportunity.risk >= 5
        human_review_required = opportunity.risk >= 8 or opportunity.reversibility <= 2

        if human_review_required:
            decision = OpportunityDecision.ESCALATE
        elif outlier_signals >= 3 and opportunity.cost <= 3 and opportunity.reversibility >= 6:
            decision = OpportunityDecision.TEST
        elif score >= 2 or outlier_signals >= 2:
            decision = OpportunityDecision.WATCH
        else:
            decision = OpportunityDecision.IGNORE

        return OpportunityAssessment(
            opportunity.id,
            score,
            decision,
            tuple(reasons),
            red_team_required,
            human_review_required,
        )

    @classmethod
    def rank(cls, opportunities: list[Opportunity]) -> list[OpportunityAssessment]:
        return sorted((cls.assess(item) for item in opportunities), key=lambda item: item.score, reverse=True)

    @classmethod
    def shortlist_tests(cls, opportunities: list[Opportunity]) -> list[OpportunityAssessment]:
        return [item for item in cls.rank(opportunities) if item.decision is OpportunityDecision.TEST]
