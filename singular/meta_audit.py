from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .learning import CalibrationRecord


class MetaAuditSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AgentCalibration:
    """Aggregate forecast performance for one decision-making component."""

    agent_id: str
    forecast_count: int
    mean_absolute_error: float
    mean_brier_score: float | None = None

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id cannot be empty")
        if self.forecast_count < 0:
            raise ValueError("forecast_count cannot be negative")
        for name, value in (("mean_absolute_error", self.mean_absolute_error),):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.mean_brier_score is not None and not 0 <= self.mean_brier_score <= 1:
            raise ValueError("mean_brier_score must be between 0 and 1")


@dataclass(frozen=True)
class MetaAuditFinding:
    code: str
    severity: MetaAuditSeverity
    subject: str
    evidence: str
    recommended_action: str


@dataclass(frozen=True)
class MetaAuditReport:
    findings: tuple[MetaAuditFinding, ...]
    healthy: bool


class MetaAuditEngine:
    """Audit the decision system itself without acquiring authority over it.

    Findings are evidence for the System Architect and human governor. This
    engine cannot rewrite agents, rules, permissions or missions.
    """

    @staticmethod
    def calibration(records: list[CalibrationRecord]) -> dict[str, float | int]:
        if not records:
            return {"count": 0, "mean_absolute_error": 0.0, "mean_brier_score": 0.0}
        brier = [record.brier_score for record in records if record.brier_score is not None]
        return {
            "count": len(records),
            "mean_absolute_error": round(sum(record.error for record in records) / len(records), 6),
            "mean_brier_score": round(sum(brier) / len(brier), 6) if brier else 0.0,
        }

    @classmethod
    def audit(
        cls,
        *,
        calibrations: list[AgentCalibration] = [],
        unknown_count: int = 0,
        contradiction_count: int = 0,
        stale_rule_count: int = 0,
        low_information_decision_count: int = 0,
    ) -> MetaAuditReport:
        findings: list[MetaAuditFinding] = []
        for calibration in sorted(calibrations, key=lambda item: item.agent_id):
            if calibration.forecast_count >= 5 and calibration.mean_absolute_error >= 0.4:
                findings.append(MetaAuditFinding(
                    "MIS_CALIBRATED_AGENT", MetaAuditSeverity.WARNING, calibration.agent_id,
                    f"MAE={calibration.mean_absolute_error:.3f} over {calibration.forecast_count} forecasts",
                    "REVIEW_FORECAST_METHOD_AND_ASSUMPTIONS",
                ))
            if calibration.mean_brier_score is not None and calibration.forecast_count >= 5 and calibration.mean_brier_score >= 0.25:
                findings.append(MetaAuditFinding(
                    "POOR_BINARY_CALIBRATION", MetaAuditSeverity.WARNING, calibration.agent_id,
                    f"Brier={calibration.mean_brier_score:.3f} over {calibration.forecast_count} forecasts",
                    "RECALIBRATE_BEFORE_HIGH_CONSEQUENCE_USE",
                ))
        if unknown_count > 0:
            findings.append(MetaAuditFinding(
                "UNRESOLVED_UNKNOWNS", MetaAuditSeverity.WARNING, "WORLD_MODEL",
                f"{unknown_count} unknown inputs remain",
                "RESOLVE_OR_EXPLICITLY_ACCEPT_UNCERTAINTY",
            ))
        if contradiction_count > 0:
            findings.append(MetaAuditFinding(
                "WORLD_MODEL_CONTRADICTION", MetaAuditSeverity.CRITICAL, "WORLD_MODEL",
                f"{contradiction_count} contradictions detected",
                "BLOCK_HIGH_CONSEQUENCE_DECISIONS_UNTIL_RESOLVED",
            ))
        if stale_rule_count > 0:
            findings.append(MetaAuditFinding(
                "STALE_RULES", MetaAuditSeverity.WARNING, "SYSTEM",
                f"{stale_rule_count} potentially obsolete rules",
                "REVIEW_RULES_AGAINST_NEW_EVIDENCE",
            ))
        if low_information_decision_count > 0:
            findings.append(MetaAuditFinding(
                "LOW_INFORMATION_DECISIONS", MetaAuditSeverity.INFO, "DECISION_ENGINE",
                f"{low_information_decision_count} decisions have weak evidence density",
                "INCREASE_EVIDENCE_CAPTURE_AND_FORECASTING",
            ))
        return MetaAuditReport(tuple(findings), not any(item.severity is MetaAuditSeverity.CRITICAL for item in findings))
