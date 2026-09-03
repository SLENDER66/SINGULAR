from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .execution_result import ExecutionResult, ExecutionStatus
from .learning import Forecast
from .learning_bridge import ExecutionLearningBridge, LearningResult
from .learning_strategy import LearningStrategyEngine, StrategyProposal


@dataclass(frozen=True)
class EconomicLearningCycle:
    """One closed economic feedback cycle, from forecast to strategy proposal."""

    forecast_id: str
    execution_status: ExecutionStatus
    learning: LearningResult
    strategy: StrategyProposal


class EconomicLearningEngine:
    """Close forecast -> execution result -> calibration -> strategy without self-mutation."""

    @staticmethod
    def evaluate(
        forecast: Forecast,
        result: ExecutionResult,
        *,
        repeated_pattern: bool = False,
    ) -> EconomicLearningCycle:
        if forecast.id != result.action_id:
            raise ValueError("forecast id must match execution action_id")
        if result.status not in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED):
            raise ValueError("Only terminal execution results can enter learning")
        learning = ExecutionLearningBridge.calibrate(
            forecast, result, repeated_pattern=repeated_pattern
        )
        strategy = LearningStrategyEngine.propose(learning.record, learning.update)
        if not isfinite(strategy.expected_improvement) or strategy.expected_improvement < 0:
            raise ValueError("strategy expected_improvement must be finite and non-negative")
        return EconomicLearningCycle(
            forecast_id=forecast.id,
            execution_status=result.status,
            learning=learning,
            strategy=strategy,
        )
