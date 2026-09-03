from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.recovery import RecoveryDecision, RecoveryManager


def _quarantined(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    contract = runtime.create_mission("recover safely", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10, contract_id=contract.mission_id)
    runtime._set_status(contract.mission_id, MissionStatus.PLANNED)
    key = store.idempotency_key("execute", contract.mission_id, action.id)
    store.begin_execution_and_start_mission(key, contract.mission_id, action.id, lease_seconds=1)
    store.mark_execution_recovery_required(key)
    return store, runtime, contract, action, key


def test_raw_execution_is_closed_even_when_recovery_exists(tmp_path: Path):
    store, runtime, contract, action, key = _quarantined(tmp_path)
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda _: True)
    assert store.get_execution(key)["status"] == "RECOVERY_REQUIRED"


def test_recovery_confirm_finalizes_without_handler_reexecution(tmp_path: Path):
    store, runtime, contract, action, key = _quarantined(tmp_path)
    result = RecoveryManager(store).resolve(
        key,
        RecoveryDecision.CONFIRM,
        result={"provider": "already_done"},
        reason="Provider reconciled externally.",
    )
    assert result.execution_status == "COMPLETED"
    assert result.mission_status == MissionStatus.COMPLETED
    assert result.result == {"provider": "already_done"}
    assert store.get_execution(key)["status"] == "COMPLETED"
    assert runtime.state(contract.mission_id).status == MissionStatus.COMPLETED


def test_recovery_fail_finalizes_without_reexecution(tmp_path: Path):
    store, runtime, contract, _, key = _quarantined(tmp_path)
    result = RecoveryManager(store).resolve(key, RecoveryDecision.FAIL, reason="Provider reports failure.")
    assert result.execution_status == "FAILED"
    assert result.mission_status == MissionStatus.FAILED
    assert result.error == "Provider reports failure."
    assert runtime.state(contract.mission_id).status == MissionStatus.FAILED


def test_recovery_cancel_finalizes_mission_without_reexecution(tmp_path: Path):
    store, runtime, contract, _, key = _quarantined(tmp_path)
    result = RecoveryManager(store).resolve(key, RecoveryDecision.CANCEL)
    assert result.execution_status == "FAILED"
    assert result.mission_status == MissionStatus.CANCELLED
    assert runtime.state(contract.mission_id).status == MissionStatus.CANCELLED


def test_recovery_cannot_be_resolved_twice(tmp_path: Path):
    store, _, _, _, key = _quarantined(tmp_path)
    manager = RecoveryManager(store)
    manager.resolve(key, RecoveryDecision.FAIL)
    with pytest.raises(ValueError, match="RECOVERY_REQUIRED"):
        manager.resolve(key, RecoveryDecision.CONFIRM, result=True)


def test_recovery_transaction_rolls_back_if_mission_cannot_finalize(tmp_path: Path):
    store, _, contract, _, key = _quarantined(tmp_path)
    store.set_mission_status(contract.mission_id, MissionStatus.COMPLETED)
    with pytest.raises(ValueError, match="RUNNING"):
        RecoveryManager(store).resolve(key, RecoveryDecision.CONFIRM, result=True)
    execution = store.get_execution(key)
    assert execution is not None
    assert execution["status"] == "RECOVERY_REQUIRED"
    assert execution["result"] is None
    assert execution["finished_at"] is not None
