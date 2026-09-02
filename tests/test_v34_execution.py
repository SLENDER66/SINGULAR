from pathlib import Path
import time

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine, ExecutionInProgress, ExecutionRecoveryRequired
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

    def fail(_):
        raise RuntimeError("boom")

    result = engine.execute(action, contract.mission_id, fail)

    assert result.status == "FAILED"
    assert result.error == "RuntimeError: boom"
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


def test_approval_is_bound_to_exact_action_fingerprint(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("human approved", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)

    changed = ActionRequest(
        action.name,
        "send a different payload",
        action.impact,
        action.risk,
        action.reversibility,
        id=action.id,
    )

    with pytest.raises(PermissionError, match="action ou son contexte a changé"):
        DurableExecutionEngine(runtime).execute(changed, contract.mission_id, lambda a: "must not run")

    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED
    assert runtime.store.get_execution(runtime.store.idempotency_key("execute", contract.mission_id, action.id)) is None


def test_approval_without_binding_fails_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("human approved", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    binding_key = runtime._approval_binding_key(approval.id)
    with runtime.store._connect() as conn:
        conn.execute("DELETE FROM idempotency WHERE key=?", (binding_key,))
    runtime.approve(approval.id)

    with pytest.raises(PermissionError, match="liaison d'identité"):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda a: "must not run")


def test_pending_escalation_cannot_execute(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("human approval", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    engine = DurableExecutionEngine(runtime)

    with pytest.raises(PermissionError, match="approbation humaine"):
        engine.execute(action, contract.mission_id, lambda a: True)

    assert runtime.state(contract.mission_id).status == MissionStatus.WAITING_APPROVAL


def test_running_execution_cannot_be_taken_over(tmp_path: Path):
    db = tmp_path / "s.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("safe automation", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    first._set_status(contract.mission_id, MissionStatus.PLANNED)
    key = first.store.idempotency_key("execute", contract.mission_id, action.id)
    first.store.begin_execution(key, contract.mission_id, action.id)
    first._set_status(contract.mission_id, MissionStatus.RUNNING)

    second = DurableMissionRuntime(DurableStore(db))
    with pytest.raises(ExecutionInProgress):
        DurableExecutionEngine(second).execute(action, contract.mission_id, lambda a: True)

    assert second.store.get_execution(key)["status"] == "RUNNING"


def test_running_execution_can_be_recovered_as_canonical_state(tmp_path: Path):
    db = tmp_path / "s.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("safe automation", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    key = first.store.idempotency_key("execute", contract.mission_id, action.id)
    first.store.begin_execution(key, contract.mission_id, action.id)

    second = DurableMissionRuntime(DurableStore(db))
    row = second.store.get_execution(key)

    assert row is not None
    assert row["status"] == "RUNNING"
    assert row["mission_id"] == contract.mission_id
    assert row["action_id"] == action.id


def test_stale_running_execution_is_quarantined_without_reexecution(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    contract = runtime.create_mission("recover safely", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    runtime.store.begin_execution(key, contract.mission_id, action.id, lease_seconds=1)
    time.sleep(1.1)

    calls = []
    with pytest.raises(ExecutionRecoveryRequired):
        DurableExecutionEngine(runtime, execution_lease_seconds=1).execute(
            action, contract.mission_id, lambda a: calls.append(a.id) or True
        )

    assert calls == []
    row = runtime.store.get_execution(key)
    assert row is not None
    assert row["status"] == "RECOVERY_REQUIRED"


def test_live_execution_lease_is_not_quarantined(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    contract = runtime.create_mission("live execution", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    runtime.store.begin_execution(key, contract.mission_id, action.id, lease_seconds=30)

    with pytest.raises(ExecutionInProgress):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda a: True)

    assert runtime.store.get_execution(key)["status"] == "RUNNING"


def test_atomic_start_cannot_leave_orphan_execution(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("atomic start", "running", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)

    with pytest.raises(ValueError, match="PLANNED"):
        runtime.store.begin_execution_and_start_mission(key, contract.mission_id, action.id)

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED
    assert runtime.store.get_execution(key) is None


def test_atomic_start_and_finish_keep_states_consistent(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("atomic lifecycle", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    runtime._set_status(contract.mission_id, MissionStatus.PLANNED)

    started = runtime.store.begin_execution_and_start_mission(key, contract.mission_id, action.id)
    assert started["claimed"] is True
    assert started["status"] == "RUNNING"
    assert runtime.state(contract.mission_id).status == MissionStatus.RUNNING

    finished = runtime.store.finish_execution_and_mission(key, "COMPLETED", result={"ok": True})
    assert finished["status"] == "COMPLETED"
    assert runtime.state(contract.mission_id).status == MissionStatus.COMPLETED


def test_atomic_finish_rejects_non_running_mission_without_partial_completion(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("atomic finish", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "execute", 1, 1, 10)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)

    runtime._set_status(contract.mission_id, MissionStatus.PLANNED)
    runtime.store.begin_execution(key, contract.mission_id, action.id)

    with pytest.raises(ValueError, match="RUNNING"):
        runtime.store.finish_execution_and_mission(key, "COMPLETED", result={"ok": True})

    row = runtime.store.get_execution(key)
    assert row is not None
    assert row["status"] == "RUNNING"
    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED
