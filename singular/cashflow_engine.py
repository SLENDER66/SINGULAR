from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class CashflowAction(str, Enum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    TEST = "TEST"
    PRIORITIZE = "PRIORITIZE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True)
class RapidCashObjective:
    target_cash: float
    horizon_days: int = 14
    protect_downside: bool = True
    preserve_long_term_optionality: bool = True

    def __post_init__(self) -> None:
        if not isfinite(self.target_cash) or self.target_cash <= 0:
            raise ValueError("target_cash must be finite and positive")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")


@dataclass(frozen=True)
class CashflowOpportunity:
    id: str
    name: str
    expected_cash: float
    probability: float
    time_to_cash_hours: float
    upfront_cost: float
    recurrence_score: float = 0.0
    skill_fit: float = 0.5
    reversibility: float = 1.0
    ownership_score: float = 0.0

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("id and name cannot be empty")
        for field_name, value in (
            ("expected_cash", self.expected_cash),
            ("time_to_cash_hours", self.time_to_cash_hours),
            ("upfront_cost", self.upfront_cost),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        for field_name, value in (
            ("probability", self.probability),
            ("recurrence_score", self.recurrence_score),
            ("skill_fit", self.skill_fit),
            ("reversibility", self.reversibility),
            ("ownership_score", self.ownership_score),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1")


@dataclass(frozen=True)
class CashflowAssessment:
    opportunity_id: str
    action: CashflowAction
    expected_value: float
    cash_velocity: float
    score: float
    reasons: tuple[str, ...]
    long_term_value: float
    human_review_required: bool


class RapidCashEngine:
    """Prioritize legitimate paths to near-term cash without sacrificing the wealth engine."""

    @staticmethod
    def assess(
        opportunity: CashflowOpportunity,
        objective: RapidCashObjective,
    ) -> CashflowAssessment:
        expected_value = opportunity.expected_cash * opportunity.probability - opportunity.upfront_cost
        velocity = opportunity.expected_cash * opportunity.probability / max(opportunity.time_to_cash_hours, 1.0)
        long_term_value = (
            0.45 * opportunity.recurrence_score
            + 0.35 * opportunity.ownership_score
            + 0.20 * opportunity.skill_fit
        )
        downside_penalty = opportunity.upfront_cost * (1.0 - opportunity.reversibility)
        score = (
            max(expected_value, 0.0)
            * (1.0 + opportunity.skill_fit)
            * (1.0 + long_term_value)
            / max(opportunity.time_to_cash_hours, 1.0)
            - downside_penalty
        )
        reasons: list[str] = []
        if opportunity.time_to_cash_hours <= 48:
            reasons.append("FAST_FIRST_CASH")
        if expected_value > 0:
            reasons.append("POSITIVE_EXPECTED_CASH")
        if opportunity.recurrence_score >= 0.7:
            reasons.append("RECURRING_CASH_FLOW")
        if opportunity.ownership_score >= 0.7:
            reasons.append("BUILDS_OWNERSHIP")
        if opportunity.upfront_cost > expected_value and objective.protect_downside:
            reasons.append("HIGH_UPFRONT_EXPOSURE")
        if opportunity.reversibility <= 0.2:
            reasons.append("LOW_REVERSIBILITY")

        human_review = (
            objective.protect_downside
            and opportunity.reversibility <= 0.2
            or opportunity.upfront_cost > objective.target_cash * 0.25
        )
        if human_review:
            action = CashflowAction.HUMAN_REVIEW
        elif expected_value <= 0:
            action = CashflowAction.IGNORE
        elif opportunity.time_to_cash_hours <= 72 and score >= 1.0:
            action = CashflowAction.PRIORITIZE
        elif opportunity.time_to_cash_hours <= objective.horizon_days * 24:
            action = CashflowAction.TEST
        else:
            action = CashflowAction.WATCH

        return CashflowAssessment(
            opportunity.id,
            action,
            round(expected_value, 6),
            round(velocity, 6),
            round(score, 6),
            tuple(reasons),
            round(long_term_value, 6),
            human_review,
        )

    @classmethod
    def rank(
        cls,
        opportunities: list[CashflowOpportunity],
        objective: RapidCashObjective,
    ) -> tuple[CashflowAssessment, ...]:
        assessments = [cls.assess(opportunity, objective) for opportunity in opportunities]
        return tuple(
            sorted(
                assessments,
                key=lambda item: (-item.score, -item.cash_velocity, item.opportunity_id),
            )
        )

    @classmethod
    def build_sprint(
        cls,
        opportunities: list[CashflowOpportunity],
        objective: RapidCashObjective,
        *,
        max_parallel_tests: int = 3,
    ) -> tuple[CashflowAssessment, ...]:
        if max_parallel_tests <= 0:
            raise ValueError("max_parallel_tests must be positive")
        ranked = cls.rank(opportunities, objective)
        return tuple(
            item
            for item in ranked
            if item.action in {CashflowAction.PRIORITIZE, CashflowAction.TEST}
        )[:max_parallel_tests]
