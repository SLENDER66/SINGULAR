import pytest

from singular.execution_result import ExecutionIntent, ExecutionResultBridge, ExecutionStatus
from singular.learning import Forecast, ForecastKind
from singular.learning_bridge import ExecutionLearningBridge


def test_binary_execution_result_closes_calibration_loop() -> None:
    forecast = Forecast("f1", ForecastKind.BINARY, probability=0.8, confidence=0.7)
    result = ExecutionResultBridge().record(
        ExecutionIntent("d1", "a1", "k1"),
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        observed_value=True,
    )
    learning = ExecutionLearningBridge.calibrate(forecast, result)
    assert learning.record.outcome == 1.0
    assert learning.record.brier_score == pytest.approx(0.04)
    assert learning.update.forecast_id == "f1"


def test_numeric_execution_result_requires_numeric_observation() -> None:
    forecast = Forecast("f1", ForecastKind.NUMERIC, expected_value=100.0)
    result = ExecutionResultBridge().record(
        ExecutionIntent("d1", "a1", "k1"),
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        observed_value=120.0,
    )
    learning = ExecutionLearningBridge.calibrate(forecast, result)
    assert learning.record.error == 20.0
    assert learning.update.recommended_action == "REVIEW_ASSUMPTIONS"


def test_non_terminal_result_cannot_calibrate() -> None:
    forecast = Forecast("f1", ForecastKind.BINARY, probability=0.8)
    result = ExecutionResultBridge().record(
        ExecutionIntent("d1", "a1", "k1"),
        status=ExecutionStatus.REJECTED,
        success=False,
        error="human rejected",
    )
    with pytest.raises(ValueError):
        ExecutionLearningBridge.calibrate(forecast, result)
