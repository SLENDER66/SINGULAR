from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ValueAssessment(str, Enum):
    ALIGNED = "aligned"
    TENSION = "tension"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class ValueMode(str, Enum):
    """How strongly a value constrains optimization."""

    HARD_CONSTRAINT = "hard_constraint"
    GUIDING = "guiding"
    OVERRIDEABLE = "overrideable"


@dataclass(frozen=True)
class CoreValue:
    name: str
    description: str = ""
    weight: float = 1.0
    mode: ValueMode = ValueMode.HARD_CONSTRAINT

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Value name must not be empty.")
        if self.weight <= 0:
            raise ValueError("Value weight must be positive.")


@dataclass(frozen=True)
class ValueAssessmentResult:
    value: CoreValue
    assessment: ValueAssessment
    rationale: str


@dataclass(frozen=True)
class Vision:
    statement: str
    horizon: str = "long_term"

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ValueError("Vision statement must not be empty.")


class ValuesEngine:
    """Treat personal values as explicit optimization inputs, not sacred axioms.

    HARD_CONSTRAINT values remain fail-closed. GUIDING/OVERRIDEABLE values may
    be challenged by evidence and tested, but are never silently rewritten.
    """

    @staticmethod
    def assess(value: CoreValue, assessment: ValueAssessment, rationale: str = "") -> ValueAssessmentResult:
        return ValueAssessmentResult(value, assessment, rationale)

    @staticmethod
    def allows_action(results: list[ValueAssessmentResult]) -> bool:
        return not any(
            r.assessment is ValueAssessment.VIOLATED and r.value.mode is ValueMode.HARD_CONSTRAINT
            for r in results
        )

    @staticmethod
    def requires_human_review(results: list[ValueAssessmentResult]) -> bool:
        return any(
            r.assessment is ValueAssessment.UNKNOWN
            or (r.assessment is ValueAssessment.VIOLATED and r.value.mode is not ValueMode.HARD_CONSTRAINT)
            for r in results
        )

    @staticmethod
    def summarize(results: list[ValueAssessmentResult]) -> dict[str, object]:
        return {
            "allowed": ValuesEngine.allows_action(results),
            "human_review": ValuesEngine.requires_human_review(results),
            "violated": [r.value.name for r in results if r.assessment is ValueAssessment.VIOLATED],
            "hard_violations": [r.value.name for r in results if r.assessment is ValueAssessment.VIOLATED and r.value.mode is ValueMode.HARD_CONSTRAINT],
            "overrideable_violations": [r.value.name for r in results if r.assessment is ValueAssessment.VIOLATED and r.value.mode is not ValueMode.HARD_CONSTRAINT],
            "unknown": [r.value.name for r in results if r.assessment is ValueAssessment.UNKNOWN],
            "tensions": [r.value.name for r in results if r.assessment is ValueAssessment.TENSION],
        }
