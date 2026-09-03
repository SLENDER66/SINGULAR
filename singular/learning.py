from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ForecastKind(str, Enum):
    BINARY = "BINARY"
    NUMERIC = "NUMERIC"


@dataclass(frozen=True)
class Forecast:
    """A prediction captured before an outcome is known."""

    id: str
    kind: ForecastKind
    probability: float | None = None
    expected_value: float | None = None
    confidence: float = 0.5
    hypothesis: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Forecast id cannot be empty")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Forecast confidence must be between 0 and 1")
        if self.kind == ForecastKind.BINARY:
            if self.probability is None or not 0 <= self.probability <= 1:
                raise ValueError("Binary forecasts require probability between 0 and 1")
        elif self.expected_value is None or not isfinite(self.expected_value):
            raise ValueError("Numeric forecasts require a finite expected_value")


@dataclass(frozen=True)
class CalibrationRecord:
    forecast_id: str
    kind: ForecastKind
    outcome: float
    error: float
    brier_score: float | None
    forecast_confidence: float
    lesson: str


@dataclass(frozen=True)
class LearningUpdate:
    """A proposed learning change; it has no authority to mutate the system."""

    forecast_id: str
    lesson: str
    hypothesis: str
    evidence_strength: float
    recommended_action: str


class LearningEngine:
    """Close the forecast -> result -> learning loop without self-modification."""

    @staticmethod
    def evaluate_binary(forecast: Forecast, outcome: bool) -> CalibrationRecord:
        if forecast.kind != ForecastKind.BINARY or forecast.probability is None:
            raise ValueError("evaluate_binary requires a BINARY forecast")
        observed = 1.0 if outcome else 0.0
        error = abs(forecast.probability - observed)
        brier = (forecast.probability - observed) ** 2
        direction = "correct" if (forecast.probability >= 0.5) == outcome else "incorrect"
        lesson = (
            f"Forecast {forecast.id} was {direction}: "
            f"predicted {forecast.probability:.2f}, observed {observed:.0f}."
        )
        return CalibrationRecord(
            forecast.id,
            forecast.kind,
            observed,
            round(error, 6),
            round(brier, 6),
            forecast.confidence,
            lesson,
        )

    @staticmethod
    def evaluate_numeric(forecast: Forecast, actual: float) -> CalibrationRecord:
        if forecast.kind != ForecastKind.NUMERIC or forecast.expected_value is None:
            raise ValueError("evaluate_numeric requires a NUMERIC forecast")
        if not isfinite(actual):
            raise ValueError("actual outcome must be finite")
        error = actual - forecast.expected_value
        direction = (
            "underestimated" if error > 0 else "overestimated" if error < 0 else "matched"
        )
        lesson = (
            f"Forecast {forecast.id} {direction}: "
            f"expected {forecast.expected_value:.4g}, observed {actual:.4g}."
        )
        return CalibrationRecord(
            forecast.id,
            forecast.kind,
            actual,
            round(abs(error), 6),
            None,
            forecast.confidence,
            lesson,
        )

    @staticmethod
    def propose_update(
        record: CalibrationRecord, *, repeated_pattern: bool = False
    ) -> LearningUpdate:
        """Turn evidence into a reviewable hypothesis, never an automatic rule change."""
        strength = min(1.0, record.forecast_confidence + (0.25 if repeated_pattern else 0.0))
        if record.kind == ForecastKind.BINARY:
            if record.brier_score is not None and record.brier_score >= 0.25:
                hypothesis = (
                    "Réduire la confiance accordée à des prévisions similaires "
                    "jusqu'à nouvelle preuve."
                )
                action = "REVIEW_FORECAST_METHOD"
            else:
                hypothesis = (
                    "Conserver la méthode et vérifier sa calibration sur "
                    "davantage de résultats."
                )
                action = "COLLECT_MORE_EVIDENCE"
        elif record.error >= 1:
            hypothesis = (
                "Réexaminer les hypothèses quantitatives qui ont produit "
                "cette estimation."
            )
            action = "REVIEW_ASSUMPTIONS"
        else:
            hypothesis = (
                "L'estimation reste compatible avec l'erreur observée; "
                "accumuler davantage de données."
            )
            action = "COLLECT_MORE_EVIDENCE"
        return LearningUpdate(
            record.forecast_id,
            record.lesson,
            hypothesis,
            round(strength, 4),
            action,
        )

    @staticmethod
    def summarize(records: list[CalibrationRecord]) -> dict[str, float | int]:
        if not records:
            return {
                "count": 0,
                "mean_absolute_error": 0.0,
                "mean_brier_score": 0.0,
                "binary_count": 0,
            }
        binary = [record for record in records if record.brier_score is not None]
        return {
            "count": len(records),
            "mean_absolute_error": round(sum(r.error for r in records) / len(records), 6),
            "mean_brier_score": round(sum(r.brier_score for r in binary) / len(binary), 6)
            if binary
            else 0.0,
            "binary_count": len(binary),
        }
