from singular.durable import DurableStore
from singular.economic_learning import EconomicLearningEngine
from singular.economic_learning_ledger import EconomicLearningLedger
from singular.execution_result import ExecutionResult, ExecutionStatus
from singular.learning import Forecast, ForecastKind


def _cycle():
    forecast = Forecast("forecast-1", ForecastKind.BINARY, probability=0.9, confidence=0.8)
    result = ExecutionResult(
        decision_id="decision-1",
        action_id="forecast-1",
        idempotency_key="idem-1",
        status=ExecutionStatus.FAILED,
        success=False,
        observed_value=False,
        error="miss",
    )
    return EconomicLearningEngine.evaluate(forecast, result)


def test_learning_cycle_survives_new_store_instance(tmp_path):
    path = tmp_path / "singular.db"
    cycle = _cycle()
    EconomicLearningLedger(DurableStore(path)).record(cycle)

    restored = EconomicLearningLedger(DurableStore(path)).get(cycle.forecast_id)

    assert restored == cycle


def test_learning_cycle_replay_is_idempotent(tmp_path):
    path = tmp_path / "singular.db"
    cycle = _cycle()
    ledger = EconomicLearningLedger(DurableStore(path))

    ledger.record(cycle)
    ledger.record(cycle)

    assert ledger.get(cycle.forecast_id) == cycle


def test_learning_cycle_tampering_is_detected(tmp_path):
    path = tmp_path / "singular.db"
    cycle = _cycle()
    ledger = EconomicLearningLedger(DurableStore(path))
    ledger.record(cycle)

    store = DurableStore(path)
    with store._connect() as conn:
        conn.execute(
            "UPDATE idempotency SET result=? WHERE key=?",
            ('{"forecast_id":"tampered"}', ledger.key_for(cycle)),
        )

    try:
        ledger.get(cycle.forecast_id)
    except RuntimeError:
        pass
    else:
        raise AssertionError("tampered learning cycle must fail closed")
