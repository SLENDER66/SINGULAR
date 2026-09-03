from dataclasses import replace

import pytest

from singular.learning import Forecast, ForecastKind, LearningEngine
from singular.outcome_ledger import OutcomeLedger
from test_validated_pipeline import AUTHORIZED_HANDLER_CAPABILITY, _build_decision


def test_outcome_ledger_records_calibration_against_attested_decision(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    forecast = Forecast("F1", ForecastKind.BINARY, probability=0.8, confidence=0.9)

    record = ledger.record(
        decision=decision,
        forecast=forecast,
        actual=True,
        execution_key="EXEC-1",
        execution_status="COMPLETED",
    )

    assert record.decision_id == decision.decision_id
    assert record.context_fingerprint == decision.context_fingerprint
    assert record.absolute_error == 0.2
    assert record.brier_score == 0.04
    assert ledger.verify()


def test_outcome_ledger_rejects_unattested_decision(tmp_path):
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    forecast = Forecast("F1", ForecastKind.BINARY, probability=0.8, confidence=0.9)
    with pytest.raises(PermissionError, match="attesté"):
        ledger.record(
            decision=_build_decision(),
            forecast=forecast,
            actual=True,
            execution_key="EXEC-1",
            execution_status="COMPLETED",
        )


def test_numeric_outcomes_preserve_signed_error(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    forecast = Forecast("F2", ForecastKind.NUMERIC, expected_value=10.0, confidence=0.8)

    record = ledger.record(
        decision=decision,
        forecast=forecast,
        actual=13.5,
        execution_key="EXEC-2",
        execution_status="COMPLETED",
    )

    expected = LearningEngine.evaluate_numeric(forecast, 13.5)
    assert record.absolute_error == expected.error
    assert record.signed_error == 3.5


def test_outcome_ledger_detects_tampering(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    forecast = Forecast("F3", ForecastKind.BINARY, probability=0.2, confidence=0.6)
    ledger.record(
        decision=decision,
        forecast=forecast,
        actual=False,
        execution_key="EXEC-3",
        execution_status="COMPLETED",
    )
    with ledger._connect() as conn:
        conn.execute("UPDATE outcome_ledger SET actual_value=1 WHERE record_id=(SELECT record_id FROM outcome_ledger LIMIT 1)")
    assert ledger.verify() is False


def test_repeated_identical_observation_is_idempotent(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    forecast = Forecast("F4", ForecastKind.BINARY, probability=0.5, confidence=0.5)
    first = ledger.record(decision=decision, forecast=forecast, actual=True, execution_key="EXEC-4", execution_status="COMPLETED")
    second = ledger.record(decision=decision, forecast=forecast, actual=True, execution_key="EXEC-4", execution_status="COMPLETED", observed_at=first.observed_at)
    assert first == second
    assert len(ledger.list()) == 1
