from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING

from .state import CapacitySnapshot
from .values import ValueAssessment, ValueAssessmentResult, ValueMode, Vision

if TYPE_CHECKING:
    from .trajectory_optimization import TrajectoryPortfolio


class TrajectoryDecision(str, Enum):
    PROCEED = "PROCEED"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class TrajectoryProfile:
    """Explicit multi-objective optimization contract for SINGULAR."""

    vision: Vision
    money: float = 1.0
    time: float = 1.0
    capability: float = 1.0
    energy: float = 1.0
    freedom: float = 1.0
    ownership: float = 1.0
    learning: float = 1.0
    resilience: float = 1.0
    transmission: float = 1.0

    def __post_init__(self) -> None:
        weights = (self.money, self.time, self.capability, self.energy, self.freedom, self.ownership, self.learning, self.resilience, self.transmission)
        if any(not isfinite(value) or value < 0 for value in weights):
            raise ValueError("Trajectory weights must be finite and non-negative")
        if not any(weights):
            raise ValueError("At least one trajectory weight must be positive")

    @property
    def weights(self) -> dict[str, float]:
        return {"money": self.money, "time": self.time, "capability": self.capability, "energy": self.energy, "freedom": self.freedom, "ownership": self.ownership, "learning": self.learning, "resilience": self.resilience, "transmission": self.transmission}


@dataclass(frozen=True)
class TrajectoryAssessment:
    decision: TrajectoryDecision
    score: float
    weighted_contribution: float
    rationale: tuple[str, ...]
    human_review: bool


class TrajectoryEngine:
    """Optimize the whole trajectory; hard constraints remain fail-closed."""

    @staticmethod
    def assess(
        profile: TrajectoryProfile,
        *,
        dimensions: dict[str, float],
        value_results: tuple[ValueAssessmentResult, ...] = (),
        capacity: CapacitySnapshot | None = None,
        portfolio: TrajectoryPortfolio | None = None,
    ) -> TrajectoryAssessment:
        unknown = sorted(set(dimensions) - set(profile.weights))
        if unknown:
            raise ValueError("Unknown trajectory dimensions: " + ", ".join(unknown))
        if any(not isfinite(value) for value in dimensions.values()):
            raise ValueError("Trajectory dimension values must be finite")

        rationale: list[str] = []
        hard_violations = [result.value.name for result in value_results if result.assessment is ValueAssessment.VIOLATED and result.value.mode is ValueMode.HARD_CONSTRAINT]
        overrideable_violations = [result.value.name for result in value_results if result.assessment is ValueAssessment.VIOLATED and result.value.mode is not ValueMode.HARD_CONSTRAINT]
        if hard_violations:
            return TrajectoryAssessment(TrajectoryDecision.BLOCK, 0.0, 0.0, ("HARD_CONSTRAINT_VIOLATION:" + ",".join(hard_violations),), True)
        if overrideable_violations:
            rationale.append("VALUE_TRADEOFF_REQUIRES_EXPLICIT_REVIEW:" + ",".join(overrideable_violations))
        if any(result.assessment is ValueAssessment.UNKNOWN for result in value_results):
            rationale.append("CORE_VALUE_STATE_UNKNOWN")

        weighted = 0.0
        total_weight = 0.0
        for name, weight in profile.weights.items():
            if weight == 0:
                continue
            if name not in dimensions:
                rationale.append(f"MISSING_DIMENSION:{name}")
                continue
            value = max(-1.0, min(1.0, dimensions[name]))
            weighted += weight * value
            total_weight += weight

        if total_weight == 0:
            return TrajectoryAssessment(TrajectoryDecision.REVIEW, 0.0, 0.0, tuple(dict.fromkeys(rationale + ["INSUFFICIENT_TRAJECTORY_DATA"])), True)

        score = round(weighted / total_weight, 6)
        if portfolio is not None:
            if not portfolio.candidates:
                return TrajectoryAssessment(TrajectoryDecision.BLOCK, 0.0, 0.0, tuple(dict.fromkeys(rationale + ["EMPTY_TRAJECTORY_PORTFOLIO"])), True)
            if not all(isfinite(value) for value in (portfolio.objective, portfolio.capacity_used, portfolio.capacity_remaining, portfolio.interaction_effect)):
                return TrajectoryAssessment(TrajectoryDecision.BLOCK, 0.0, 0.0, tuple(dict.fromkeys(rationale + ["INVALID_TRAJECTORY_PORTFOLIO"])), True)
            if portfolio.objective <= 0:
                return TrajectoryAssessment(TrajectoryDecision.BLOCK, 0.0, 0.0, tuple(dict.fromkeys(rationale + ["NON_POSITIVE_TRAJECTORY_PORTFOLIO"])), True)
            if portfolio.capacity_used < 0 or portfolio.capacity_remaining < 0:
                return TrajectoryAssessment(TrajectoryDecision.BLOCK, 0.0, 0.0, tuple(dict.fromkeys(rationale + ["INVALID_TRAJECTORY_CAPACITY"])), True)
            if portfolio.interaction_effect < 0:
                rationale.append("NEGATIVE_PORTFOLIO_INTERACTION")

        if capacity is not None and capacity.confidence < 0.5:
            rationale.append("LOW_CAPACITY_CONFIDENCE")
        if capacity is not None and capacity.headroom <= 0:
            rationale.append("NO_CAPACITY_HEADROOM")

        human_review = bool(rationale)
        if score < 0:
            decision = TrajectoryDecision.BLOCK
            rationale.append("NEGATIVE_GLOBAL_TRAJECTORY")
        elif score < 0.35 or human_review:
            decision = TrajectoryDecision.REVIEW
        else:
            decision = TrajectoryDecision.PROCEED

        return TrajectoryAssessment(decision, score, round(weighted, 6), tuple(dict.fromkeys(rationale)), human_review)
