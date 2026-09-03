from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine, ExecutionInProgress, ExecutionRecoveryRequired
from singular.mission_runtime import DurableMissionRuntime


def test_raw_execution_api_is_disabled(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("safe automation", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda _: {"ok": True})

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED


def test_raw_execution_cannot_be_used_for_pending_human_approval(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("human approval", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda _: True)

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED


def test_raw_recovery_takeover_path_is_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("recover safely", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    runtime._set_status(contract.mission_id, MissionStatus.PLANNED)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    runtime.store.begin_execution(key, contract.mission_id, action.id, lease_seconds=1)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        DurableExecutionEngine(runtime, execution_lease_seconds=1).execute(action, contract.mission_id, lambda _: True)


def test_durable_engine_still_exposes_recovery_state_without_raw_execution(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("recover safely", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    runtime._set_status(contract.mission_id, MissionStatus.PLANNED)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    runtime.store.begin_execution(key, contract.mission_id, action.id)

    row = runtime.store.get_execution(key)
    assert row is not None
    assert row["status"] == "RUNNING"
    assert row["action_id"] == action.id
