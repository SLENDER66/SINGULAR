from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine, ExecutionInProgress
from singular.mission_runtime import DurableMissionRuntime


def test_authorized_execution_is_transactional_and_durable(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    contract = runtime.create_mission("safe automation", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    calls = []

    first = engine.execute(action, contract.mission_id, lambda a: calls.append(a.id) or {"ok": True})
    second_runtime = DurableMissionRuntime(DurableStore(db))
    second = DurableExecutionEngine(second_runtime).execute(action, contract.mission_id, lambda a: calls.append("DUPLICATE"))

    assert first.status == "COMPLETED"
    assert second == first
    assert calls == [action.id]
    assert second_runtime.state(contract.mission_id).status == MissionStatus.COMPLETED


def test_execution_failure_is_durable_and_mission_fails(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("safe automation", "done", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)

    result = engine.execute(action, contract.mission_id, lambda a: (_ for _ in ()).throw(RuntimeError("boom")))

    assert result.status == "FAILED"
    assert "RuntimeError: boom" == result.error
    assert runtime.state(contract.mission_id).status == MissionStatus.FAILED
    assert runtime.store.get_execution(result.execution_key)["status"] == "FAILED"


def test_prepare_action_cannot_execute(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("prepare only", "plan", autonomy=Autonomy.PREPARE)
    action = ActionRequest("safe_action", "prepare", 1, 1, 10)

    with pytest.raises(PermissionError, match="préparée mais non autorisée"):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda a: True)

    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED


def test_approved_escalation_can_execute(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("human approved", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    engine = DurableExecutionEngine(runtime)

    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)

    result = engine.execute(action, contract.mission_id, lambda a: "sent")

    assert result.status == "COMPLETED"
    assert result.result == "sent"
    assert runtime.state(contract.mission_id).status == MissionStatus.COMPLETED


def test_pending_escalation_cannot_execute(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("human approval", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    engine = DurableExecutionEngine(runtime)

    with pytest.raises(PermissionError, match="approbation humaine"):
        engine.execute(action, contract.mission_id, lambda a: True)

    assert runtime.state(contract.mission_id).status == MissionStatus.WAITING_APPROVAL


def test_execution_claim_is_single_writer(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    key = store.idempotency_key("execute", "MIS-1", "ACT-1")
    first = store.begin_execution(key, "MIS-1", "ACT-1")
    second = store.begin_execution(key, "MIS-1", "ACT-1")

    assert first["status"] == "RUNNING"
    assert second["status"] == "RUNNING"
    assert first["started_at"] == second["started_at"]

    with pytest.raises(ExecutionInProgress):
        raise ExecutionInProgress(key)
