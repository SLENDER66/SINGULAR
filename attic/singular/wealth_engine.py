from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class WealthAction(str, Enum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    TEST = "TEST"
    PRIORITIZE = "PRIORITIZE"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass(frozen=True)
class WealthObjective:
    """North-star objective for durable, risk-adjusted wealth creation."""

    target: str = "MAXIMIZE_DURABLE_RISK_ADJUSTED_NET_WORTH"
    horizon_years: int = 20
    protect_downside: bool = True
    preserve_optionality: bool = True

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError("target must be non-empty")
        if self.horizon_years <= 0:
            raise ValueError("horizon_years must be positive")


@dataclass(frozen=True)
class WealthOpportunity:
    """Economic opportunity; ``time`` is expressed in years."""

    id: str
    expected_wealth_delta: float
    probability: float
    downside: float
    cost: float
    time: float
    ownership: float
    compounding: float
    optionality: float
    reversibility: float

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("opportunity id cannot be empty")
        if not isfinite(self.expected_wealth_delta):
            raise ValueError("expected_wealth_delta must be finite")
        for name, value in (
            ("probability", self.probability),
            ("ownership", self.ownership),
            ("compounding", self.compounding),
            ("optionality", self.optionality),
            ("reversibility", self.reversibility),
        ):
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        for name, value in (("downside", self.downside), ("cost", self.cost), ("time", self.time)):
            if value < 0 or not isfinite(value):
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class WealthAssessment:
    opportunity_id: str
    score: float
    action: WealthAction
    expected_value: float
    reasons: tuple[str, ...]


class WealthEngine:
    """Translate the wealth objective into disciplined economic priorities."""

    @staticmethod
    def assess(
        opportunity: WealthOpportunity,
        objective: WealthObjective | None = None,
    ) -> WealthAssessment:
        objective = objective or WealthObjective()
        expected_value = opportunity.expected_wealth_delta * opportunity.probability
        upside = max(0.0, expected_value)
        risk_penalty = opportunity.downside * (
            1.25 if opportunity.reversibility < 0.3 else 0.75
        )
        downside_factor = 1.0
        if objective.protect_downside:
            downside_factor = max(0.1, 1.0 - opportunity.downside)
        else:
            risk_penalty *= 0.5
        friction = 1.0 + opportunity.cost + 0.25 * opportunity.time
        ownership_factor = 1.0 + opportunity.ownership
        compounding_factor = 1.0 + opportunity.compounding
        optionality_factor = 1.0 + (
            opportunity.optionality
            if objective.preserve_optionality
            else 0.5 * opportunity.optionality
        )
        horizon_factor = 1.0 if opportunity.time <= objective.horizon_years else 0.5
        score = (
            upside
            * downside_factor
            * ownership_factor
            * compounding_factor
            * optionality_factor
            * horizon_factor
            - risk_penalty
        ) / friction
        score = round(score, 6)

        reasons: list[str] = [
            f"OBJECTIVE={objective.target}",
            f"HORIZON_YEARS={objective.horizon_years}",
        ]
        if objective.protect_downside:
            reasons.append("DOWNSIDE_PROTECTED")
        if objective.preserve_optionality:
            reasons.append("OPTIONALITY_PRESERVED")
        if opportunity.ownership >= 0.7:
            reasons.append("HIGH_OWNERSHIP")
        if opportunity.compounding >= 0.7:
            reasons.append("HIGH_COMPOUNDING")
        if opportunity.optionality >= 0.7:
            reasons.append("HIGH_OPTIONALITY")
        if opportunity.downside >= 0.7:
            reasons.append("HIGH_DOWNSIDE")
        if opportunity.time >= 5:
            reasons.append("SLOW_FEEDBACK")
        if opportunity.time > objective.horizon_years:
            reasons.append("BEYOND_OBJECTIVE_HORIZON")

        if (
            objective.protect_downside
            and opportunity.downside >= 0.9
            and opportunity.reversibility <= 0.2
        ):
            action = WealthAction.HUMAN_REVIEW
        elif score >= 10 and opportunity.cost <= 3 and opportunity.reversibility >= 0.6:
            action = WealthAction.PRIORITIZE
        elif score > 0 and opportunity.cost <= 4 and opportunity.reversibility >= 0.5:
            action = WealthAction.TEST
        elif score > 0:
            action = WealthAction.WATCH
        else:
            action = WealthAction.IGNORE

        return WealthAssessment(
            opportunity.id, score, action, round(expected_value, 6), tuple(reasons)
        )

    @classmethod
    def rank(
        cls,
        opportunities: list[WealthOpportunity],
        objective: WealthObjective | None = None,
    ) -> tuple[WealthAssessment, ...]:
        assessments = [cls.assess(item, objective) for item in opportunities]
        return tuple(sorted(assessments, key=lambda item: (-item.score, item.opportunity_id)))

    @classmethod
    def capital_stack(cls) -> tuple[str, ...]:
        return (
            "PROTECT_BASE: eliminate ruin risk and preserve liquidity",
            "INCREASE_EARNING_POWER: scarce skills, network, credibility, career leverage",
            "BUILD_OWNERSHIP: businesses, equity, intellectual property and other productive assets",
            "ALLOCATE_CAPITAL: reinvest where expected risk-adjusted return is strongest",
            "COMPOUND: reinvest cash flow and gains into productive ownership",
            "PROTECT_PATRIMONY: legal, tax, diversification, insurance and succession review",
            "BUILD_EMPIRE: durable organizations, systems, brands and capital allocation capability",
        )
