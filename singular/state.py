from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StateDimension(str, Enum):
    MENTAL = "mental"
    PHYSICAL = "physical"
    ENERGY = "energy"
    FOCUS = "focus"
    EMOTIONAL = "emotional"
    SOCIAL = "social"
    FINANCIAL = "financial"
    PROFESSIONAL = "professional"
    ENVIRONMENT = "environment"
    MOTIVATION = "motivation"
    CAPACITY = "capacity"


@dataclass(frozen=True)
class StateObservation:
    dimension: StateDimension
    level: float
    confidence: float = 1.0
    note: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.level <= 1:
            raise ValueError("State level must be between 0 and 1.")
        if not 0 <= self.confidence <= 1:
            raise ValueError("State confidence must be between 0 and 1.")


@dataclass(frozen=True)
class CapacitySnapshot:
    available: float
    load: float
    constraint: float = 0.0
    confidence: float = 1.0

    def __post_init__(self) -> None:
        for value in (self.available, self.load, self.constraint, self.confidence):
            if not 0 <= value <= 1:
                raise ValueError("Capacity values must be between 0 and 1.")

    @property
    def headroom(self) -> float:
        return round(max(0.0, self.available - self.load - self.constraint), 3)


class CapacityEngine:
    """Convert current state into a conservative execution capacity signal.

    This is a planning aid, not a medical or psychological diagnostic system.
    Unknown or low-confidence state should reduce automation ambition rather than
    trigger stronger assumptions.
    """

    @staticmethod
    def snapshot(observations: list[StateObservation]) -> CapacitySnapshot:
        if not observations:
            return CapacitySnapshot(available=0.0, load=1.0, confidence=0.0)
        by_dimension = {item.dimension: item for item in observations}
        available = by_dimension.get(StateDimension.CAPACITY)
        load = 1.0 - by_dimension.get(StateDimension.ENERGY, StateObservation(StateDimension.ENERGY, 0.0)).level
        focus = by_dimension.get(StateDimension.FOCUS, StateObservation(StateDimension.FOCUS, 0.0)).level
        constraint = 1.0 - focus
        if available is not None:
            capacity = available.level
            confidence = available.confidence
        else:
            capacity = (by_dimension.get(StateDimension.ENERGY, StateObservation(StateDimension.ENERGY, 0.0)).level + focus) / 2
            confidence = min(
                by_dimension.get(StateDimension.ENERGY, StateObservation(StateDimension.ENERGY, 0.0)).confidence,
                by_dimension.get(StateDimension.FOCUS, StateObservation(StateDimension.FOCUS, 0.0)).confidence,
            )
        return CapacitySnapshot(capacity, load, constraint, confidence)

    @staticmethod
    def can_absorb(snapshot: CapacitySnapshot, effort: float) -> bool:
        if not 0 <= effort <= 1:
            raise ValueError("Effort must be between 0 and 1.")
        return effort <= snapshot.headroom

    @staticmethod
    def recommendation(snapshot: CapacitySnapshot, effort: float) -> str:
        if snapshot.confidence < 0.5:
            return "CLARIFY_STATE"
        if CapacityEngine.can_absorb(snapshot, effort):
            return "PROCEED"
        if snapshot.headroom > 0:
            return "REDUCE_SCOPE"
        return "DEFER_OR_DROP"
