from __future__ import annotations

from dataclasses import dataclass

from .execution_result import ExecutionResult, ExecutionStatus
from .learning import CalibrationRecord, Forecast, LearningEngine, LearningUpdate


@dataclass(frozen=True)
class LearningResult:
    """Calibration output derived from an observed execution result."""

    record: CalibrationRecord
    update: LearningUpdate


class ExecutionLearningBridge:
    """Translate observed execution outcomes into reviewable learning evidence."""

    @staticmethod
    def calibrate(
        forecast: Forecast,
        result: ExecutionResult,
        *,
        repeated_pattern: bool = False,
    ) -> LearningResult:
        if result.status not in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED):
            raise ValueError("Only terminal execution results can calibrate a forecast")
        if result.observed_value is None:
            raise ValueError("A terminal result requires observed_value for calibration")

        if forecast.kind.value == "BINARY":
            if not isinstance(result.observed_value, bool):
                raise TypeError("Binary calibration requires a boolean observed_value")
            record = LearningEngine.evaluate_binary(forecast, result.observed_value)
        else:
            if isinstance(result.observed_value, bool) or not isinstance(result.observed_value, (int, float)):
                raise TypeError("Numeric calibration requires a numeric observed_value")
            record = LearningEngine.evaluate_numeric(forecast, float(result.observed_value))

        update = LearningEngine.propose_update(record, repeated_pattern=repeated_pattern)
        return LearningResult(record, update)
