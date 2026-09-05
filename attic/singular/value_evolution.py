from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ValueEvolutionDisposition(str, Enum):
    KEEP = "KEEP"
    QUESTION = "QUESTION"
    TEST = "TEST"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ValueHypothesis:
    """A proposal to question a current preference without silently rewriting it."""

    value_name: str
    current_position: str
    alternative_position: str
    expected_gain: float
    downside: float = 0.0
    reversibility: float = 1.0
    evidence_strength: float = 0.0

    def __post_init__(self) -> None:
        if not self.value_name.strip() or not self.current_position.strip() or not self.alternative_position.strip():
            raise ValueError("value hypothesis fields cannot be empty")
        for name, value in (("expected_gain", self.expected_gain), ("downside", self.downside), ("reversibility", self.reversibility), ("evidence_strength", self.evidence_strength)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.downside < 0 or not 0 <= self.reversibility <= 1 or not 0 <= self.evidence_strength <= 1:
            raise ValueError("invalid value hypothesis bounds")


@dataclass(frozen=True)
class ValueEvolutionAssessment:
    disposition: ValueEvolutionDisposition
    score: float
    reasons: tuple[str, ...]
    human_review: bool


class ValueEvolutionEngine:
    """Continuously challenges preferences while preserving explicit governance."""

    @staticmethod
    def assess(hypothesis: ValueHypothesis) -> ValueEvolutionAssessment:
        score = hypothesis.expected_gain * (0.5 + 0.5 * hypothesis.evidence_strength) - hypothesis.downside
        reasons: list[str] = []
        if hypothesis.evidence_strength < 0.5:
            reasons.append("INSUFFICIENT_EVIDENCE")
        if hypothesis.reversibility <= 0.2:
            reasons.append("LOW_REVERSIBILITY")
        if score <= 0:
            reasons.append("NO_CLEAR_NET_GAIN")
            disposition = ValueEvolutionDisposition.KEEP if hypothesis.evidence_strength >= 0.5 else ValueEvolutionDisposition.QUESTION
        elif hypothesis.evidence_strength < 0.7:
            disposition = ValueEvolutionDisposition.TEST
            reasons.append("BOUNDED_TEST_RECOMMENDED")
        else:
            disposition = ValueEvolutionDisposition.REVIEW
            reasons.append("VALUE_CHANGE_REQUIRES_EXPLICIT_REVIEW")
        return ValueEvolutionAssessment(
            disposition,
            round(score, 6),
            tuple(dict.fromkeys(reasons)),
            hypothesis.reversibility <= 0.2 or disposition is ValueEvolutionDisposition.REVIEW,
        )

    @staticmethod
    def compare(current_score: float, alternative_score: float) -> ValueEvolutionAssessment:
        """Compare two positions without treating the alternative as automatically superior."""
        if not isfinite(current_score) or not isfinite(alternative_score):
            raise ValueError("scores must be finite")
        delta = alternative_score - current_score
        if delta > 0:
            return ValueEvolutionAssessment(
                ValueEvolutionDisposition.REVIEW,
                round(delta, 6),
                ("ALTERNATIVE_OUTPERFORMS_CURRENT", "EXPLICIT_REVIEW_REQUIRED"),
                True,
            )
        if delta < 0:
            return ValueEvolutionAssessment(
                ValueEvolutionDisposition.KEEP,
                round(delta, 6),
                ("CURRENT_OUTPERFORMS_ALTERNATIVE",),
                False,
            )
        return ValueEvolutionAssessment(
            ValueEvolutionDisposition.QUESTION,
            0.0,
            ("NO_MEASURED_DIFFERENCE",),
            True,
        )
