from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime


def test_approval_cannot_cross_missions(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    first = runtime.create_mission("first", "done", autonomy=Autonomy.PREPARE)
    second = runtime.create_mission("second", "done", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    runtime.route(action, first.mission_id)
    approval = runtime.store.pending_approvals(first.mission_id)[0]
    runtime.approve(approval.id)

    forged = ActionRequest("send_application", "send", 5, 6, 6, id=action.id, contract_id=second.mission_id)
    with pytest.raises(ValueError, match="ne correspond pas au contrat"):
        runtime.route(forged, second.mission_id)


def test_forbidden_action_is_case_sensitive_safe(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission(
        "security", "safe", autonomy=Autonomy.EXECUTE_AUTHORIZED,
        forbidden_actions=("delete_account",),
    )
    result = runtime.route(ActionRequest("delete_account", "delete", 1, 1, 10), contract.mission_id)
    assert result.governor.mode == Autonomy.BLOCK
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_capability_cannot_be_swapped_after_approval(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("email", "sent", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_email", "send", 2, 5, 6, capability="send_email")
    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)

    swapped = ActionRequest(
        action.name, action.description, action.impact, action.risk, action.reversibility,
        capability="modify_github", id=action.id,
    )
    with pytest.raises(ValueError, match="Identité d'action réutilisée"):
        DurableExecutionEngine(runtime).execute(swapped, contract.mission_id, lambda _: "must not run")


def test_missing_native_binding_cannot_execute(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("email", "sent", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_email", "send", 2, 5, 6, capability="send_email")
    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)

    with runtime.store._connect() as conn:
        conn.execute("DELETE FROM approval_bindings WHERE approval_id=?", (approval.id,))

    with pytest.raises(PermissionError, match="liaison d'identité"):
        DurableExecutionEngine(runtime).execute(action, contract.mission_id, lambda _: "must not run")
