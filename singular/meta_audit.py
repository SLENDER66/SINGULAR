from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping, Sequence

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
        if not isfinite(self.mean_absolute_error) or self.mean_absolute_error < 0:
            raise ValueError("mean_absolute_error must be finite and non-negative")
        if self.mean_brier_score is not None and (
            not isfinite(self.mean_brier_score) or not 0 <= self.mean_brier_score <= 1
        ):
            raise ValueError("mean_brier_score must be finite and between 0 and 1")


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
    """Audit the decision system itself without acquiring authority over it."""

    @staticmethod
    def calibration(records: Sequence[CalibrationRecord]) -> dict[str, float | int]:
        if not records:
            return {"count": 0, "mean_absolute_error": 0.0, "mean_brier_score": 0.0}
        total_error = 0.0
        brier_total = 0.0
        brier_count = 0
        for record in records:
            total_error += record.error
            if record.brier_score is not None:
                brier_total += record.brier_score
                brier_count += 1
        return {
            "count": len(records),
            "mean_absolute_error": round(total_error / len(records), 6),
            "mean_brier_score": round(brier_total / brier_count, 6) if brier_count else 0.0,
        }

    @classmethod
    def audit_learning(
        cls,
        records_by_agent: Mapping[str, Sequence[CalibrationRecord]],
        *,
        minimum_sample: int = 5,
    ) -> MetaAuditReport:
        """Audit raw learning records by agent; emits findings only, never mutations."""
        if minimum_sample < 1:
            raise ValueError("minimum_sample must be positive")
        calibrations: list[AgentCalibration] = []
        for agent_id, records in records_by_agent.items():
            summary = cls.calibration(records)
            has_brier = any(record.brier_score is not None for record in records)
            calibrations.append(
                AgentCalibration(
                    agent_id=agent_id,
                    forecast_count=int(summary["count"]),
                    mean_absolute_error=float(summary["mean_absolute_error"]),
                    mean_brier_score=(float(summary["mean_brier_score"]) if has_brier else None),
                )
            )
        return cls.audit(calibrations=tuple(calibrations), minimum_sample=minimum_sample)

    @classmethod
    def audit(
        cls,
        *,
        calibrations: tuple[AgentCalibration, ...] = (),
        unknown_count: int = 0,
        contradiction_count: int = 0,
        stale_rule_count: int = 0,
        low_information_decision_count: int = 0,
        minimum_sample: int = 5,
    ) -> MetaAuditReport:
        del cls
        if minimum_sample < 1:
            raise ValueError("minimum_sample must be positive")
        for name, value in (
            ("unknown_count", unknown_count),
            ("contradiction_count", contradiction_count),
            ("stale_rule_count", stale_rule_count),
            ("low_information_decision_count", low_information_decision_count),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative")

        findings: list[MetaAuditFinding] = []
        for calibration in sorted(calibrations, key=lambda item: item.agent_id):
            if calibration.forecast_count >= minimum_sample and calibration.mean_absolute_error >= 0.4:
                findings.append(
                    MetaAuditFinding(
                        "MIS_CALIBRATED_AGENT",
                        MetaAuditSeverity.WARNING,
                        calibration.agent_id,
                        f"MAE={calibration.mean_absolute_error:.3f} over {calibration.forecast_count} forecasts",
                        "REVIEW_FORECAST_METHOD_AND_ASSUMPTIONS",
                    )
                )
            if (
                calibration.mean_brier_score is not None
                and calibration.forecast_count >= minimum_sample
                and calibration.mean_brier_score >= 0.25
            ):
                findings.append(
                    MetaAuditFinding(
                        "POOR_BINARY_CALIBRATION",
                        MetaAuditSeverity.WARNING,
                        calibration.agent_id,
                        f"Brier={calibration.mean_brier_score:.3f} over {calibration.forecast_count} forecasts",
                        "RECALIBRATE_BEFORE_HIGH_CONSEQUENCE_USE",
                    )
                )
        if unknown_count > 0:
            findings.append(MetaAuditFinding("UNRESOLVED_UNKNOWNS", MetaAuditSeverity.WARNING, "WORLD_MODEL", f"{unknown_count} unknown inputs remain", "RESOLVE_OR_EXPLICITLY_ACCEPT_UNCERTAINTY"))
        if contradiction_count > 0:
            findings.append(MetaAuditFinding("WORLD_MODEL_CONTRADICTION", MetaAuditSeverity.CRITICAL, "WORLD_MODEL", f"{contradiction_count} contradictions detected", "BLOCK_HIGH_CONSEQUENCE_DECISIONS_UNTIL_RESOLVED"))
        if stale_rule_count > 0:
            findings.append(MetaAuditFinding("STALE_RULES", MetaAuditSeverity.WARNING, "SYSTEM", f"{stale_rule_count} potentially obsolete rules", "REVIEW_RULES_AGAINST_NEW_EVIDENCE"))
        if low_information_decision_count > 0:
            findings.append(MetaAuditFinding("LOW_INFORMATION_DECISIONS", MetaAuditSeverity.INFO, "DECISION_ENGINE", f"{low_information_decision_count} decisions have weak evidence density", "INCREASE_EVIDENCE_CAPTURE_AND_FORECASTING"))
        return MetaAuditReport(
            tuple(findings),
            not any(item.severity is MetaAuditSeverity.CRITICAL for item in findings),
        )
