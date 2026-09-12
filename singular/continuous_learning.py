"""Governed continuous-learning loop for validated decisions.

The loop turns executed decisions into durable observations and reviewable
learning proposals. It deliberately stops before policy mutation: learning can
produce a proposal, never silently rewrite execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .decision_attestation import DecisionAttestationStore
from .learning import Forecast
from .learning_review_queue import LearningReview, LearningReviewQueue
from .outcome_ledger import OutcomeLedger, OutcomeObservation
from .validated_trajectory_decision import ValidatedTrajectoryDecision


@dataclass(frozen=True)
class LearningCycleResult:
    outcome: OutcomeObservation
    review: LearningReview


class ContinuousLearningCycle:
    """Record an outcome and create one human-reviewable learning proposal."""

    def __init__(
        self,
        path: str | Path = "data/singular.db",
        *,
        attestation_store: DecisionAttestationStore | None = None,
    ) -> None:
        self.path = Path(path)
        self.attestation_store = attestation_store or DecisionAttestationStore(self.path)
        self.outcomes = OutcomeLedger(self.path, attestation_store=self.attestation_store)
        self.reviews = LearningReviewQueue(self.path)

    def observe(
        self,
        *,
        decision: ValidatedTrajectoryDecision,
        forecast: Forecast,
        actual: bool | float,
        execution_key: str,
        execution_status: str,
        repeated_pattern: bool = False,
        observed_at: str | None = None,
    ) -> LearningCycleResult:
        outcome = self.outcomes.record(
            decision=decision,
            forecast=forecast,
            actual=actual,
            execution_key=execution_key,
            execution_status=execution_status,
            observed_at=observed_at,
        )
        review = self.reviews.propose(outcome, repeated_pattern=repeated_pattern)
        return LearningCycleResult(outcome, review)

    def verify(self) -> bool:
        return self.outcomes.verify()


__all__ = ["LearningCycleResult", "ContinuousLearningCycle"]
