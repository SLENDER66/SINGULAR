from singular.durable import DurableStore, MissionStatus
from singular.learning import Forecast, ForecastKind, LearningEngine
from singular.outcome_ledger import OutcomeLedger
from tests.support import executed_decision
from tests.test_validated_pipeline import _build_decision


def _completed_execution(decision, db_path):
    store = DurableStore(db_path)
    store.save_mission(decision.contract)
    store.set_mission_status(decision.contract.mission_id, MissionStatus.PLANNED)
    key = store.idempotency_key("execute", decision.contract.mission_id, decision.global_report.action_id)
    store.begin_execution_and_start_mission(key, decision.contract.mission_id, decision.global_report.action_id)
    store.finish_execution_and_mission(key, "COMPLETED", result={"ok": True})
    return key


def test_outcome_ledger_records_calibration_against_attested_decision(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F1", ForecastKind.BINARY, probability=0.8, confidence=0.9)

    record = ledger.record(
        decision=decision,
        forecast=forecast,
        actual=True,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )

    assert record.decision_id == decision.decision_id
    assert record.context_fingerprint == decision.context_fingerprint
    assert record.absolute_error == 0.2
    assert record.brier_score == 0.04
    assert ledger.verify()


def test_outcome_ledger_rejects_unattested_decision(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    forecast = Forecast("F1", ForecastKind.BINARY, probability=0.8, confidence=0.9)
    try:
        ledger.record(
            decision=decision,
            forecast=forecast,
            actual=True,
            execution_key="EXEC-1",
            execution_status="COMPLETED",
        )
    except PermissionError as exc:
        # The refusal message is in English here; the test matched a French
        # fragment, so an unattested decision would have satisfied it only by
        # raising some other PermissionError.
        assert "durably issued" in str(exc)
    else:
        raise AssertionError("unattested decision must be rejected")


def test_outcome_ledger_rejects_fake_execution(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    forecast = Forecast("F-FAKE", ForecastKind.BINARY, probability=0.8, confidence=0.9)
    key = DurableStore.idempotency_key("execute", decision.contract.mission_id, decision.global_report.action_id)
    try:
        ledger.record(decision=decision, forecast=forecast, actual=True, execution_key=key, execution_status="COMPLETED")
    except PermissionError as exc:
        assert "Aucune exécution durable" in str(exc)
    else:
        raise AssertionError("missing durable execution must be rejected")


def test_numeric_outcomes_preserve_signed_error(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F2", ForecastKind.NUMERIC, expected_value=10.0, confidence=0.8)

    record = ledger.record(
        decision=decision,
        forecast=forecast,
        actual=13.5,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )

    expected = LearningEngine.evaluate_numeric(forecast, 13.5)
    assert record.absolute_error == expected.error
    assert record.signed_error == 3.5


def test_outcome_ledger_detects_tampering(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F3", ForecastKind.BINARY, probability=0.2, confidence=0.6)
    ledger.record(
        decision=decision,
        forecast=forecast,
        actual=False,
        execution_key=execution_key,
        execution_status="COMPLETED",
    )
    with ledger._connect() as conn:
        conn.execute("UPDATE outcome_ledger SET actual_value=1 WHERE record_id=(SELECT record_id FROM outcome_ledger LIMIT 1)")
    assert ledger.verify() is False


def test_repeated_identical_observation_is_idempotent(tmp_path):
    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    forecast = Forecast("F4", ForecastKind.BINARY, probability=0.5, confidence=0.5)
    first = ledger.record(decision=decision, forecast=forecast, actual=True, execution_key=execution_key, execution_status="COMPLETED")
    second = ledger.record(decision=decision, forecast=forecast, actual=True, execution_key=execution_key, execution_status="COMPLETED", observed_at=first.observed_at)
    assert first == second
    assert len(ledger.list()) == 1


def test_recorded_observation_carries_the_forecast_kind_as_an_enum(tmp_path):
    """A str that only compares equal is not the enum consumers test with `is`.

    record() built the observation from a payload holding forecast.kind.value,
    so the object it returned carried "BINARY" rather than ForecastKind.BINARY.
    Every `record.kind is ForecastKind.BINARY` check downstream was False, and a
    binary forecast was scored with the continuous formula -- which is how a
    Brier score of 0.81 produced HOLD with no human review instead of the
    recalibration branch.
    """
    executed = executed_decision(tmp_path / "kinds.db")
    ledger = OutcomeLedger(tmp_path / "kinds.db", attestation_store=executed.engine.attestation_store)
    forecast = Forecast("F-KIND", ForecastKind.BINARY, probability=0.9, confidence=0.9)
    recorded = ledger.record(
        decision=executed.decision,
        forecast=forecast,
        actual=False,
        execution_key=executed.execution_key,
        execution_status=executed.execution_status,
    )

    assert recorded.forecast_kind is ForecastKind.BINARY
    assert ledger.list()[-1].forecast_kind is ForecastKind.BINARY
    assert ledger.verify() is True


def test_a_confident_binary_forecast_that_was_wrong_reaches_recalibration(tmp_path):
    """The consequence the type loss hid, asserted end to end."""
    from singular.learning import CalibrationRecord, LearningEngine
    from singular.learning_strategy import LearningStrategyEngine, StrategyDisposition

    executed = executed_decision(tmp_path / "recalibrate.db")
    ledger = OutcomeLedger(tmp_path / "recalibrate.db", attestation_store=executed.engine.attestation_store)
    forecast = Forecast("F-MISS", ForecastKind.BINARY, probability=0.9, confidence=0.95)
    outcome = ledger.record(
        decision=executed.decision,
        forecast=forecast,
        actual=False,
        execution_key=executed.execution_key,
        execution_status=executed.execution_status,
    )
    assert outcome.brier_score >= 0.25

    record = CalibrationRecord(
        forecast_id=outcome.forecast_id,
        kind=outcome.forecast_kind,
        outcome=outcome.actual_value,
        error=outcome.absolute_error,
        brier_score=outcome.brier_score,
        forecast_confidence=outcome.forecast_confidence,
        lesson=outcome.lesson,
    )
    strategy = LearningStrategyEngine.propose(record, LearningEngine.propose_update(record))
    assert strategy.disposition is StrategyDisposition.TEST
    assert strategy.human_review_required is True


def test_concurrent_records_keep_one_unbroken_chain(tmp_path):
    """Two writers reading the same tail would each link to it, and verify() walks in order.

    A fork needs no tampering to appear and cannot be repaired afterwards: the
    ledger is append-only, so an honest race would leave it permanently
    unverifiable.
    """
    import threading

    decision = _build_decision()
    ledger = OutcomeLedger(tmp_path / "outcomes.db")
    ledger.attestation_store.issue(decision)
    execution_key = _completed_execution(decision, tmp_path / "outcomes.db")
    errors: list[Exception] = []
    barrier = threading.Barrier(6)

    def record(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            ledger.record(
                decision=decision,
                forecast=Forecast(f"F{index}", ForecastKind.BINARY, probability=0.8, confidence=0.9),
                actual=True,
                execution_key=execution_key,
                execution_status="COMPLETED",
            )
        except Exception as exc:  # noqa: BLE001 - reported through the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=record, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert len(ledger.list()) == 6
    assert ledger.verify()
