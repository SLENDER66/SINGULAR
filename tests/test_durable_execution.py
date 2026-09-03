import pytest

from singular.durable import DurableStore
from singular.durable_execution import DurableExecutionLedger
from singular.execution_result import ExecutionIntent, ExecutionResult, ExecutionStatus


def test_execution_result_survives_new_store_instance(tmp_path) -> None:
    db = tmp_path / "singular.db"
    result = ExecutionResult(
        "decision-1",
        "action-1",
        "idem-1",
        ExecutionStatus.SUCCEEDED,
        True,
        observed_value=42,
        metadata=(("source", '"test"'),),
    )

    first = DurableExecutionLedger(DurableStore(db))
    assert first.record(result) == result

    second = DurableExecutionLedger(DurableStore(db))
    assert second.get("idem-1") == result
    assert second.record(result) == result


def test_durable_ledger_rejects_idempotency_reuse_with_different_result(tmp_path) -> None:
    db = tmp_path / "singular.db"
    ledger = DurableExecutionLedger(DurableStore(db))
    original = ExecutionResult(
        "decision-1", "action-1", "idem-1", ExecutionStatus.SUCCEEDED, True, observed_value=42
    )
    changed = ExecutionResult(
        "decision-1", "action-1", "idem-1", ExecutionStatus.SUCCEEDED, True, observed_value=43
    )

    ledger.record(original)
    with pytest.raises(ValueError, match="réutilisée"):
        ledger.record(changed)


def test_record_intent_normalizes_metadata_and_persists(tmp_path) -> None:
    db = tmp_path / "singular.db"
    ledger = DurableExecutionLedger(DurableStore(db))
    intent = ExecutionIntent("decision-1", "action-1", "idem-1")

    result = ledger.record_intent(
        intent,
        status=ExecutionStatus.FAILED,
        success=False,
        error="network",
        metadata={"z": 2, "a": True},
    )

    assert result.metadata == (("a", "true"), ("z", "2"))
    assert ledger.get("idem-1") == result
