"""Bounded self-improvement orchestration.

SINGULAR may learn from measured outcomes and construct strategy proposals, but
accepted proposals are still review artifacts. No automatic strategy or policy
mutation occurs in this layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .learning import CalibrationRecord, LearningEngine
from .learning_review_queue import LearningReview, LearningReviewQueue
from .learning_strategy import LearningStrategyEngine, StrategyProposal
from .outcome_ledger import OutcomeLedger, OutcomeObservation
from .validated_trajectory_decision import ValidatedTrajectoryDecision
from .learning import Forecast


@dataclass(frozen=True)
class SelfImprovementProposal:
    outcome: OutcomeObservation
    review: LearningReview
    strategy: StrategyProposal
    mutation_authorized: bool = False

    def __post_init__(self) -> None:
        if self.mutation_authorized:
            raise ValueError("self-improvement proposals cannot authorize mutation")
        if self.review.outcome_record_id != self.outcome.record_id:
            raise ValueError("learning review must reference the observed outcome")
        if self.strategy.forecast_id != self.outcome.forecast_id:
            raise ValueError("strategy proposal must reference the observed forecast")


class SelfImprovementEngine:
    """Turn measured outcomes into reviewable strategy proposals."""

    def __init__(self, path: str | Path = "data/singular.db") -> None:
        self.outcomes = OutcomeLedger(path)
        self.reviews = LearningReviewQueue(path)

    def propose(
        self,
        *,
        decision: ValidatedTrajectoryDecision,
        forecast: Forecast,
        actual: bool | float,
        execution_key: str,
        execution_status: str,
        repeated_pattern: bool = False,
        observed_at: str | None = None,
    ) -> SelfImprovementProposal:
        outcome = self.outcomes.record(
            decision=decision,
            forecast=forecast,
            actual=actual,
            execution_key=execution_key,
            execution_status=execution_status,
            observed_at=observed_at,
        )
        review = self.reviews.propose(outcome, repeated_pattern=repeated_pattern)
        record = CalibrationRecord(
            forecast_id=outcome.forecast_id,
            kind=outcome.forecast_kind,
            outcome=outcome.actual_value,
            error=outcome.absolute_error,
            brier_score=outcome.brier_score,
            forecast_confidence=outcome.forecast_confidence,
            lesson=outcome.lesson,
        )
        update = LearningEngine.propose_update(record, repeated_pattern=repeated_pattern)
        strategy = LearningStrategyEngine.propose(record, update)
        return SelfImprovementProposal(outcome, review, strategy)

    def verify(self) -> bool:
        return self.outcomes.verify()


__all__ = ["SelfImprovementProposal", "SelfImprovementEngine"]
