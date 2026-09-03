from dataclasses import replace

import pytest

from singular.learning import Forecast, ForecastKind
from singular.learning_review_queue import LearningReviewQueue
from singular.outcome_ledger import OutcomeLedger
from test_validated_pipeline import _build_decision


def test_learning_review_is_reviewable_not_automatic_mutation(tmp_path):
    decision = _build_decision()
    outcomes = OutcomeLedger(tmp_path / "learning.db")
    outcomes.attestation_store.issue(decision)
    forecast = Forecast("F-QUEUE", ForecastKind.BINARY, probability=0.9, confidence=0.9)
    outcome = outcomes.record(
        decision=decision,
        forecast=forecast,
        actual=False,
        execution_key="EXEC-QUEUE",
        execution_status="COMPLETED",
        observed_at="2026-09-03T18:00:00+00:00",
    )

    queue = LearningReviewQueue(tmp_path / "learning.db")
    review = queue.propose(outcome)

    assert review.status == "PENDING"
    assert review.outcome_record_id == outcome.record_id
    assert review.evidence_strength == 0.9
    assert queue.pending() == (review,)


def test_learning_review_rejects_forged_or_unpersisted_outcome(tmp_path):
    decision = _build_decision()
    outcomes = OutcomeLedger(tmp_path / "learning.db")
    outcomes.attestation_store.issue(decision)
    forecast = Forecast("F-FORGED", ForecastKind.BINARY, probability=0.8, confidence=0.8)
    outcome = outcomes.record(
        decision=decision,
        forecast=forecast,
        actual=True,
        execution_key="EXEC-FORGED",
        execution_status="COMPLETED",
    )
    queue = LearningReviewQueue(tmp_path / "learning.db")
    forged = replace(outcome, actual_value=0.0)
    with pytest.raises(PermissionError, match="exact persisted outcome"):
        queue.propose(forged)


def test_learning_review_requires_explicit_accept_or_reject(tmp_path):
    decision = _build_decision()
    outcomes = OutcomeLedger(tmp_path / "learning.db")
    outcomes.attestation_store.issue(decision)
    forecast = Forecast("F-REVIEW", ForecastKind.BINARY, probability=0.9, confidence=0.9)
    outcome = outcomes.record(decision=decision, forecast=forecast, actual=False, execution_key="EXEC-REVIEW", execution_status="COMPLETED")
    queue = LearningReviewQueue(tmp_path / "learning.db")
    review = queue.propose(outcome)

    with pytest.raises(ValueError, match="ACCEPTED or REJECTED"):
        queue.review(review.review_id, "AUTO_APPLY")
    accepted = queue.review(review.review_id, "ACCEPTED")
    assert accepted.status == "ACCEPTED"
    assert queue.pending() == ()


def test_learning_review_cannot_be_reprocessed_after_final_decision(tmp_path):
    decision = _build_decision()
    outcomes = OutcomeLedger(tmp_path / "learning.db")
    outcomes.attestation_store.issue(decision)
    forecast = Forecast("F-IDEM", ForecastKind.BINARY, probability=0.2, confidence=0.7)
    outcome = outcomes.record(decision=decision, forecast=forecast, actual=True, execution_key="EXEC-IDEM", execution_status="COMPLETED")
    queue = LearningReviewQueue(tmp_path / "learning.db")
    review = queue.propose(outcome)
    queue.review(review.review_id, "REJECTED")
    with pytest.raises(KeyError):
        queue.review(review.review_id, "ACCEPTED")
