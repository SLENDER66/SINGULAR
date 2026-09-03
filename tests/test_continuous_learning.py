from singular.continuous_learning import ContinuousLearningCycle
from singular.learning import Forecast, ForecastKind
from test_validated_pipeline import _build_decision


def test_continuous_learning_cycle_closes_observation_to_review(tmp_path):
    decision = _build_decision()
    cycle = ContinuousLearningCycle(tmp_path / "continuous.db")
    cycle.attestation_store.issue(decision)
    forecast = Forecast("F-CYCLE", ForecastKind.BINARY, probability=0.9, confidence=0.9)

    result = cycle.observe(
        decision=decision,
        forecast=forecast,
        actual=False,
        execution_key="EXEC-CYCLE",
        execution_status="COMPLETED",
        repeated_pattern=True,
        observed_at="2026-09-03T18:30:00+00:00",
    )

    assert result.outcome.decision_id == decision.decision_id
    assert result.review.status == "PENDING"
    assert result.review.recommended_action == "REVIEW_FORECAST_METHOD"
    assert cycle.verify() is True


def test_continuous_learning_cycle_reuses_same_review_for_same_outcome(tmp_path):
    decision = _build_decision()
    cycle = ContinuousLearningCycle(tmp_path / "continuous.db")
    cycle.attestation_store.issue(decision)
    forecast = Forecast("F-CYCLE-IDEM", ForecastKind.BINARY, probability=0.5, confidence=0.8)
    kwargs = dict(
        decision=decision,
        forecast=forecast,
        actual=True,
        execution_key="EXEC-CYCLE-IDEM",
        execution_status="COMPLETED",
        observed_at="2026-09-03T18:31:00+00:00",
    )

    first = cycle.observe(**kwargs)
    second = cycle.observe(**kwargs)
    assert first.outcome == second.outcome
    assert first.review == second.review
