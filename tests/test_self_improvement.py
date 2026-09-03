from singular.learning import Forecast, ForecastKind
from singular.self_improvement import SelfImprovementEngine
from test_validated_pipeline import _build_decision


def test_self_improvement_produces_testable_strategy_without_mutation(tmp_path):
    decision = _build_decision()
    engine = SelfImprovementEngine(tmp_path / "self-improvement.db")
    engine.outcomes.attestation_store.issue(decision)
    forecast = Forecast("F-SELF", ForecastKind.BINARY, probability=0.9, confidence=0.95)

    proposal = engine.propose(
        decision=decision,
        forecast=forecast,
        actual=False,
        execution_key="EXEC-SELF",
        execution_status="COMPLETED",
        repeated_pattern=True,
        observed_at="2026-09-03T19:00:00+00:00",
    )

    assert proposal.mutation_authorized is False
    assert proposal.review.status == "PENDING"
    assert proposal.strategy.forecast_id == forecast.id
    assert proposal.strategy.human_review_required is True
    assert engine.verify() is True
