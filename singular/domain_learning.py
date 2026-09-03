from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class LearningDomain(str, Enum):
    """Domains SINGULAR can improve without changing its core governance rules."""

    PSYCHOLOGY = "psychology"
    NUTRITION = "nutrition"
    PHYSICAL = "physical"
    SLEEP = "sleep"
    FINANCE = "finance"
    CAREER = "career"
    BUSINESS = "business"
    INVESTING = "investing"
    COMMUNICATION = "communication"
    RELATIONSHIPS = "relationships"
    LEADERSHIP = "leadership"
    LEARNING = "learning"
    KNOWLEDGE = "knowledge"
    TECHNOLOGY = "technology"
    DECISION_MAKING = "decision_making"
    PRODUCTIVITY = "productivity"
    RESILIENCE = "resilience"
    PERSONAL_PRESENCE = "personal_presence"
    GOVERNANCE = "governance"
    OTHER = "other"


class LearningDisposition(str, Enum):
    HOLD = "HOLD"
    TEST = "TEST"
    REVIEW = "REVIEW"
    ADOPT_PROPOSAL = "ADOPT_PROPOSAL"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class DomainObservation:
    """A measured observation; it is not automatically treated as truth."""

    domain: LearningDomain
    metric: str
    before: float
    after: float
    confidence: float = 0.5
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (("before", self.before), ("after", self.after), ("confidence", self.confidence)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.metric.strip():
            raise ValueError("metric cannot be empty")

    @property
    def delta(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class DomainHypothesis:
    domain: LearningDomain
    hypothesis: str
    intervention: str
    expected_improvement: float
    cost: float = 0.0
    risk: float = 0.0
    reversibility: float = 1.0
    evidence_strength: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("expected_improvement", self.expected_improvement),
            ("cost", self.cost),
            ("risk", self.risk),
            ("reversibility", self.reversibility),
            ("evidence_strength", self.evidence_strength),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.cost < 0 or self.risk < 0:
            raise ValueError("cost and risk cannot be negative")
        if not 0 <= self.reversibility <= 1:
            raise ValueError("reversibility must be between 0 and 1")
        if not 0 <= self.evidence_strength <= 1:
            raise ValueError("evidence_strength must be between 0 and 1")
        if not self.hypothesis.strip() or not self.intervention.strip():
            raise ValueError("hypothesis and intervention cannot be empty")


@dataclass(frozen=True)
class DomainLearningResult:
    domain: LearningDomain
    disposition: LearningDisposition
    score: float
    reasons: tuple[str, ...]
    human_review: bool


class UniversalLearningEngine:
    """A domain-agnostic improvement loop: observe -> hypothesize -> test -> learn.

    It deliberately never diagnoses a person, prescribes medical treatment, or
    mutates SINGULAR's rules. Domain-specific expertise can constrain proposals,
    while governance remains shared and fail-closed.
    """

    @staticmethod
    def assess_observation(observation: DomainObservation) -> dict[str, float | str]:
        return {
            "domain": observation.domain.value,
            "metric": observation.metric,
            "delta": round(observation.delta, 6),
            "confidence": observation.confidence,
            "evidence_count": len(observation.evidence_refs),
        }

    @staticmethod
    def evaluate(
        hypothesis: DomainHypothesis,
        *,
        observations: tuple[DomainObservation, ...] = (),
        sensitive: bool = False,
    ) -> DomainLearningResult:
        reasons: list[str] = []
        matching = [item for item in observations if item.domain is hypothesis.domain]
        observed_delta = sum(item.delta for item in matching) / len(matching) if matching else None

        if hypothesis.risk >= 8:
            return DomainLearningResult(
                hypothesis.domain,
                LearningDisposition.BLOCK,
                -1.0,
                ("RISK_TOO_HIGH",),
                True,
            )
        if sensitive or hypothesis.reversibility <= 0.2:
            reasons.append("HUMAN_REVIEW_REQUIRED")
        if not matching:
            reasons.append("INSUFFICIENT_DOMAIN_DATA")
        elif observed_delta is not None:
            if observed_delta <= 0:
                reasons.append("OBSERVED_RESULT_NOT_POSITIVE")
            else:
                reasons.append("OBSERVED_RESULT_POSITIVE")

        score = (
            hypothesis.expected_improvement * (0.5 + 0.5 * hypothesis.evidence_strength)
            - hypothesis.cost
            - 0.5 * hypothesis.risk
        )
        if not isfinite(score):
            raise ValueError("learning score must be finite")
        score = round(score, 6)

        if score <= 0:
            disposition = LearningDisposition.REVIEW
            reasons.append("NON_POSITIVE_EXPECTED_VALUE")
        elif hypothesis.evidence_strength < 0.5 or not matching:
            disposition = LearningDisposition.TEST
        elif observed_delta is not None and observed_delta > 0:
            disposition = LearningDisposition.ADOPT_PROPOSAL
            reasons.append("ADOPTION_REQUIRES_GOVERNANCE")
        else:
            disposition = LearningDisposition.REVIEW

        return DomainLearningResult(
            hypothesis.domain,
            disposition,
            score,
            tuple(dict.fromkeys(reasons)),
            bool(sensitive or hypothesis.reversibility <= 0.2),
        )

    @staticmethod
    def improve(
        observations: tuple[DomainObservation, ...],
        hypotheses: tuple[DomainHypothesis, ...],
    ) -> tuple[DomainLearningResult, ...]:
        """Evaluate all domain hypotheses as one portfolio, preserving dissent."""
        return tuple(
            UniversalLearningEngine.evaluate(
                hypothesis,
                observations=observations,
                sensitive=hypothesis.domain
                in {LearningDomain.PSYCHOLOGY, LearningDomain.NUTRITION, LearningDomain.PHYSICAL, LearningDomain.SLEEP},
            )
            for hypothesis in hypotheses
        )
