from singular.learning import Forecast, ForecastKind, LearningEngine
from singular.learning_strategy import LearningStrategyEngine, StrategyDisposition


def test_large_binary_error_becomes_bounded_test() -> None:
    forecast = Forecast("f1", ForecastKind.BINARY, probability=0.9, confidence=0.8)
    record = LearningEngine.evaluate_binary(forecast, False)
    update = LearningEngine.propose_update(record)

    proposal = LearningStrategyEngine.propose(record, update)

    assert proposal.disposition is StrategyDisposition.TEST
    assert proposal.human_review_required is True
    assert proposal.test_plan == "RECALIBRATE_FORECAST_METHOD_ON_HISTORICAL_SAMPLE"


def test_small_repeated_numeric_error_can_be_adopted_after_review() -> None:
    forecast = Forecast("f2", ForecastKind.NUMERIC, expected_value=100, confidence=0.9)
    record = LearningEngine.evaluate_numeric(forecast, 100.05)
    update = LearningEngine.propose_update(record, repeated_pattern=True)

    proposal = LearningStrategyEngine.propose(record, update)

    assert proposal.disposition is StrategyDisposition.ADOPT
    assert proposal.human_review_required is False


def test_mismatched_learning_artifacts_are_rejected() -> None:
    first = Forecast("f3", ForecastKind.NUMERIC, expected_value=10)
    second = Forecast("f4", ForecastKind.NUMERIC, expected_value=10)
    record = LearningEngine.evaluate_numeric(first, 11)
    update = LearningEngine.propose_update(
        LearningEngine.evaluate_numeric(second, 10.5)
    )

    try:
        LearningStrategyEngine.propose(record, update)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "forecast_id" in str(exc)
