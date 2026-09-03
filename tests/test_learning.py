import pytest

from singular.learning import Forecast, ForecastKind, LearningEngine


def test_binary_forecast_produces_brier_score() -> None:
    forecast = Forecast("f1", ForecastKind.BINARY, probability=0.8, confidence=0.7)

    record = LearningEngine.evaluate_binary(forecast, True)

    assert record.error == pytest.approx(0.2)
    assert record.brier_score == pytest.approx(0.04)
    assert record.kind == ForecastKind.BINARY


def test_bad_binary_forecast_produces_reviewable_learning_update() -> None:
    forecast = Forecast("f2", ForecastKind.BINARY, probability=0.9, confidence=0.8)
    record = LearningEngine.evaluate_binary(forecast, False)

    update = LearningEngine.propose_update(record)

    assert update.recommended_action == "REVIEW_FORECAST_METHOD"
    assert "confiance" in update.hypothesis.lower()


def test_numeric_forecast_preserves_signed_error_as_lesson() -> None:
    forecast = Forecast("f3", ForecastKind.NUMERIC, expected_value=10.0)

    record = LearningEngine.evaluate_numeric(forecast, 13.0)

    assert record.error == pytest.approx(3.0)
    assert "underestimated" in record.lesson


def test_summary_is_deterministic() -> None:
    records = [
        LearningEngine.evaluate_binary(Forecast("a", ForecastKind.BINARY, probability=0.8), True),
        LearningEngine.evaluate_binary(Forecast("b", ForecastKind.BINARY, probability=0.2), False),
    ]

    summary = LearningEngine.summarize(records)

    assert summary == {
        "count": 2,
        "mean_absolute_error": 0.2,
        "mean_brier_score": 0.04,
        "binary_count": 2,
    }


def test_invalid_forecast_is_rejected() -> None:
    with pytest.raises(ValueError):
        Forecast("bad", ForecastKind.BINARY, probability=1.1)
