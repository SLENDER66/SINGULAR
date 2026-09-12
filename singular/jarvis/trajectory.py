"""Deterministic prioritization primitives for JARVIS.

These rules encode SINGULAR's trajectory philosophy without giving the LLM any
authority. The model may describe candidates; deterministic code decides how
candidate properties combine for prioritization. A low-cost experiment is
favored when uncertainty is high, while hard governance remains elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TrajectoryCandidate:
    """A proposed intervention evaluated as part of the global trajectory."""

    name: str
    impact: float
    risk: float
    reversibility: float
    leverage: float = 5.0
    dependency: float = 5.0
    uncertainty: float = 5.0
    cost: float = 5.0
    learning: float = 5.0
    ownership: float = 0.0
    recurrence: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("candidate name is required")
        for field in (
            "impact", "risk", "reversibility", "leverage", "dependency",
            "uncertainty", "cost", "learning", "ownership", "recurrence",
        ):
            value = getattr(self, field)
            if not isfinite(value) or not 0.0 <= value <= 10.0:
                raise ValueError(f"{field} must be finite and between 0 and 10")


@dataclass(frozen=True)
class TrajectoryPriority:
    """Deterministic priority; this is not a governance authorization."""

    score: float
    test_first: bool
    reasons: tuple[str, ...]


def prioritize(candidate: TrajectoryCandidate) -> TrajectoryPriority:
    """Score global leverage while penalizing risk, cost and uncertainty.

    The formula deliberately rewards reversible learning and optionality rather
    than treating immediate impact as the sole objective. It never returns an
    authorization decision.
    """
    global_leverage = (
        candidate.impact * 0.30
        + candidate.leverage * 0.20
        + candidate.dependency * 0.15
        + candidate.learning * 0.10
        + candidate.ownership * 0.10
        + candidate.recurrence * 0.15
    )
    downside = candidate.risk * 0.35 + candidate.cost * 0.20 + candidate.uncertainty * 0.20
    reversibility_bonus = candidate.reversibility * 0.25
    score = max(0.0, min(100.0, (global_leverage - downside + reversibility_bonus) * 10.0))
    test_first = candidate.uncertainty >= 7.0 and candidate.reversibility >= 7.0
    reasons: list[str] = []
    if candidate.dependency >= 7.0:
        reasons.append("HIGH_DEPENDENCY_LEVERAGE")
    if candidate.leverage >= 7.0:
        reasons.append("HIGH_LEVERAGE")
    if candidate.uncertainty >= 7.0:
        reasons.append("HIGH_UNCERTAINTY")
    if candidate.reversibility >= 7.0:
        reasons.append("REVERSIBLE")
    if candidate.ownership >= 7.0:
        reasons.append("OWNERSHIP")
    if candidate.recurrence >= 7.0:
        reasons.append("RECURRENCE")
    if test_first:
        reasons.append("LOW_COST_TEST_FIRST")
    return TrajectoryPriority(round(score, 4), test_first, tuple(reasons))


__all__ = ["TrajectoryCandidate", "TrajectoryPriority", "prioritize"]
