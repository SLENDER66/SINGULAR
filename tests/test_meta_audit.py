import pytest

from singular.learning import Forecast, ForecastKind, LearningEngine
from singular.meta_audit import AgentCalibration, MetaAuditEngine, MetaAuditSeverity


def test_critical_world_model_contradiction_marks_system_unhealthy() -> None:
    report = MetaAuditEngine.audit(contradiction_count=1)

    assert report.healthy is False
    assert report.findings[0].severity is MetaAuditSeverity.CRITICAL
    assert report.findings[0].code == "WORLD_MODEL_CONTRADICTION"


def test_miscalibration_is_warning_not_self_modification() -> None:
    report = MetaAuditEngine.audit(
        calibrations=(AgentCalibration("finance", 10, 0.5, 0.3),)
    )

    assert report.healthy is True
    assert [finding.code for finding in report.findings] == [
        "MIS_CALIBRATED_AGENT",
        "POOR_BINARY_CALIBRATION",
    ]
    assert all("REVIEW" in finding.recommended_action or "RECALIBRATE" in finding.recommended_action for finding in report.findings)


def test_calibration_summary_is_deterministic() -> None:
    records = [
        LearningEngine.evaluate_binary(Forecast("a", ForecastKind.BINARY, probability=0.8), True),
        LearningEngine.evaluate_binary(Forecast("b", ForecastKind.BINARY, probability=0.2), False),
    ]

    assert MetaAuditEngine.calibration(records) == {
        "count": 2,
        "mean_absolute_error": 0.2,
        "mean_brier_score": 0.04,
    }


def test_learning_records_are_aggregated_by_agent() -> None:
    records = [
        LearningEngine.evaluate_binary(Forecast(f"f{i}", ForecastKind.BINARY, probability=0.9), False)
        for i in range(5)
    ]

    report = MetaAuditEngine.audit_learning({"finance": records})

    assert report.healthy is True
    assert [finding.code for finding in report.findings] == [
        "MIS_CALIBRATED_AGENT",
        "POOR_BINARY_CALIBRATION",
    ]
    assert report.findings[0].subject == "finance"


def test_learning_meta_audit_does_not_flag_small_samples() -> None:
    record = LearningEngine.evaluate_binary(
        Forecast("small", ForecastKind.BINARY, probability=0.99), False
    )

    report = MetaAuditEngine.audit_learning({"finance": [record]})

    assert report.findings == ()
    assert report.healthy is True


def test_minimum_sample_must_be_positive() -> None:
    with pytest.raises(ValueError, match="minimum_sample must be positive"):
        MetaAuditEngine.audit(minimum_sample=0)


def test_negative_audit_counter_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        MetaAuditEngine.audit(unknown_count=-1)
