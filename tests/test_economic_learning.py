import pytest

from singular.economic_learning import EconomicLearningEngine
from singular.execution_result import ExecutionResult, ExecutionStatus
from singular.learning import Forecast, ForecastKind
from singular.learning_strategy import StrategyDisposition


def result(action_id: str, observed: bool) -> ExecutionResult:
    return ExecutionResult(
        decision_id="d1",
        action_id=action_id,
        idempotency_key="k1",
        status=ExecutionStatus.SUCCEEDED if observed else ExecutionStatus.FAILED,
        success=observed,
        observed_value=observed,
        error=None if observed else "test failure",
    )


def test_economic_learning_cycle_produces_reviewable_strategy() -> None:
    forecast = Forecast("cash-test", ForecastKind.BINARY, probability=0.9, confidence=0.8)
    cycle = EconomicLearningEngine.evaluate(forecast, result("cash-test", False))
    assert cycle.forecast_id == "cash-test"
    assert cycle.learning.record.error == 0.9
    assert cycle.strategy.disposition is StrategyDisposition.TEST
    assert cycle.strategy.human_review_required is True


def test_economic_learning_rejects_mismatched_forecast_and_action() -> None:
    forecast = Forecast("cash-test", ForecastKind.BINARY, probability=0.5)
    with pytest.raises(ValueError, match="match"):
        EconomicLearningEngine.evaluate(forecast, result("other-action", True))


def test_non_terminal_result_cannot_enter_learning() -> None:
    forecast = Forecast("cash-test", ForecastKind.BINARY, probability=0.5)
    pending = ExecutionResult("d1", "cash-test", "k2", ExecutionStatus.AUTHORIZED, False)
    with pytest.raises(ValueError, match="terminal"):
        EconomicLearningEngine.evaluate(forecast, pending)
