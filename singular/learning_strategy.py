from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .learning import CalibrationRecord, ForecastKind, LearningUpdate


class StrategyDisposition(str, Enum):
    HOLD = "HOLD"
    REVIEW = "REVIEW"
    TEST = "TEST"
    ADOPT = "ADOPT"


@dataclass(frozen=True)
class StrategyProposal:
    """Reviewable strategy change; it never mutates system policy by itself."""

    forecast_id: str
    disposition: StrategyDisposition
    hypothesis: str
    evidence: str
    test_plan: str
    expected_improvement: float
    human_review_required: bool


class LearningStrategyEngine:
    """Convert measured forecast error into bounded, testable strategy proposals."""

    @staticmethod
    def propose(record: CalibrationRecord, update: LearningUpdate) -> StrategyProposal:
        if record.forecast_id != update.forecast_id:
            raise ValueError("record and update forecast_id must match")
        if not isfinite(record.error) or record.error < 0:
            raise ValueError("record error must be finite and non-negative")
        if not isfinite(update.evidence_strength) or not 0 <= update.evidence_strength <= 1:
            raise ValueError("evidence_strength must be finite and within [0, 1]")

        if record.kind is ForecastKind.BINARY:
            if record.brier_score is None or not isfinite(record.brier_score):
                raise ValueError("binary calibration requires a finite brier_score")
            severity = min(max(record.brier_score, 0.0), 1.0)
            expected = round(severity * update.evidence_strength, 6)
            if record.brier_score >= 0.25:
                return StrategyProposal(
                    record.forecast_id,
                    StrategyDisposition.TEST,
                    update.hypothesis,
                    update.lesson,
                    "RECALIBRATE_FORECAST_METHOD_ON_HISTORICAL_SAMPLE",
                    expected,
                    True,
                )
        else:
            expected = round(
                min(record.error / (1.0 + record.error), 1.0)
                * update.evidence_strength,
                6,
            )
            if record.error >= 1.0:
                return StrategyProposal(
                    record.forecast_id,
                    StrategyDisposition.TEST,
                    update.hypothesis,
                    update.lesson,
                    "RETEST_ASSUMPTIONS_WITH_A_BOUNDED_LOW_COST_EXPERIMENT",
                    expected,
                    True,
                )

        if update.evidence_strength >= 0.8 and record.error <= 0.1:
            return StrategyProposal(
                record.forecast_id,
                StrategyDisposition.ADOPT,
                update.hypothesis,
                update.lesson,
                "REPLICATE_RESULT_BEFORE_GENERALIZING",
                round(update.evidence_strength * (1.0 - record.error), 6),
                False,
            )

        return StrategyProposal(
            record.forecast_id,
            StrategyDisposition.HOLD,
            update.hypothesis,
            update.lesson,
            "COLLECT_MORE_OUTCOMES_BEFORE_CHANGING_STRATEGY",
            expected,
            False,
        )
