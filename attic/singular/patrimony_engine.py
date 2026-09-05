from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class FailureDisposition(str, Enum):
    CONTAIN = "CONTAIN"
    LEARN = "LEARN"
    TEST_AGAIN = "TEST_AGAIN"


@dataclass(frozen=True)
class FailureRecord:
    id: str
    objective: str
    expected: float
    actual: float
    cost: float
    reversible: bool
    lesson: str | None = None
    validated: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.objective.strip():
            raise ValueError("failure id and objective cannot be empty")
        for name, value in (("expected", self.expected), ("actual", self.actual), ("cost", self.cost)):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.validated and not self.lesson:
            raise ValueError("a validated failure must contain a lesson")


@dataclass(frozen=True)
class FailureConversion:
    failure_id: str
    error: float
    disposition: FailureDisposition
    learning_asset: str
    next_test: str | None


@dataclass(frozen=True)
class PatrimonyAssessment:
    generations: int
    ownership_continuity: float
    governance: float
    systemization: float
    succession: float
    resilience: float
    score: float
    priorities: tuple[str, ...]


class PatrimonyEngine:
    """Convert setbacks into reusable learning and measure continuity."""

    @staticmethod
    def convert_failure(failure: FailureRecord) -> FailureConversion:
        error = abs(failure.actual - failure.expected)
        if failure.validated:
            return FailureConversion(
                failure.id,
                round(error, 6),
                FailureDisposition.TEST_AGAIN if failure.reversible else FailureDisposition.CONTAIN,
                failure.lesson or "VALIDATED_LESSON",
                "RUN_CONTROLLED_RETEST" if failure.reversible else None,
            )
        if failure.reversible:
            return FailureConversion(
                failure.id,
                round(error, 6),
                FailureDisposition.LEARN,
                "CAPTURE_CAUSE_AND_UPDATE_FORECAST",
                "DESIGN_LOW_COST_VALIDATION_TEST",
            )
        return FailureConversion(
            failure.id,
            round(error, 6),
            FailureDisposition.CONTAIN,
            "CAPTURE_ROOT_CAUSE_BEFORE_RETRY",
            None,
        )

    @staticmethod
    def assess(
        *,
        generations: int,
        ownership_continuity: float,
        governance: float,
        systemization: float,
        succession: float,
        resilience: float,
    ) -> PatrimonyAssessment:
        if generations < 0:
            raise ValueError("generations must be non-negative")
        values = {
            "ownership_continuity": ownership_continuity,
            "governance": governance,
            "systemization": systemization,
            "succession": succession,
            "resilience": resilience,
        }
        for name, value in values.items():
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and between 0 and 1")

        score = round(sum(values.values()) / len(values), 6)
        priorities: list[str] = []
        if ownership_continuity < 0.7:
            priorities.append("PROTECT_OWNERSHIP_CONTINUITY")
        if governance < 0.7:
            priorities.append("BUILD_GOVERNANCE")
        if systemization < 0.7:
            priorities.append("SYSTEMIZE_BEYOND_FOUNDER")
        if succession < 0.7:
            priorities.append("PREPARE_SUCCESSION")
        if resilience < 0.7:
            priorities.append("BUILD_FAILURE_RECOVERY_CAPACITY")
        if not priorities and generations >= 2:
            priorities.append("COMPOUND_AND_TRANSMIT")

        return PatrimonyAssessment(
            generations,
            ownership_continuity,
            governance,
            systemization,
            succession,
            resilience,
            score,
            tuple(priorities),
        )
