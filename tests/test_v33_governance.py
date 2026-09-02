from dataclasses import replace
from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy, ApprovalStatus
from singular.durable import DurableStore, MissionStatus
from singular.mission_runtime import DurableMissionRuntime


def test_orange_action_escalates_and_persists_approval(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    result = runtime.route(ActionRequest("send_application", "send", 5, 6, 6), contract.mission_id)
    assert result.governor.mode == Autonomy.ESCALATE
    assert result.governor.approval_id
    pending = runtime.store.pending_approvals()
    assert len(pending) == 1
    assert pending[0].status == ApprovalStatus.PENDING
    assert runtime.state(contract.mission_id).status == MissionStatus.WAITING_APPROVAL

    runtime.approve(pending[0].id)
    assert runtime.store.pending_approvals() == ()
    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED


def test_rejected_approval_blocks_mission(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    runtime.route(ActionRequest("send_application", "send", 5, 6, 6), contract.mission_id)
    approval = runtime.store.pending_approvals()[0]
    runtime.reject(approval.id)
    assert runtime.store.pending_approvals() == ()
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_approval_commands_are_idempotent_and_terminal_statuses_are_protected(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    runtime.route(ActionRequest("send_application", "send", 5, 6, 6), contract.mission_id)
    approval = runtime.store.pending_approvals()[0]
    runtime.approve(approval.id)
    runtime.approve(approval.id)
    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED
    with pytest.raises(ValueError, match="déjà validée"):
        runtime.reject(approval.id)


def test_route_is_idempotent_for_replayed_action(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    first = runtime.route(action, contract.mission_id)
    second = runtime.route(action, contract.mission_id)
    assert second == first
    pending = runtime.store.pending_approvals(contract.mission_id)
    assert len(pending) == 1
    assert pending[0].id == first.governor.approval_id


def test_replayed_action_id_with_different_payload_fails_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    runtime.route(action, contract.mission_id)
    tampered = replace(action, description="different payload")
    with pytest.raises(ValueError, match="contenu différent"):
        runtime.route(tampered, contract.mission_id)
    assert len(runtime.store.pending_approvals(contract.mission_id)) == 1


def test_red_and_black_actions_fail_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("finance", "safe plan", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    red = runtime.route(ActionRequest("high_risk", "danger", 8, 8, 6), contract.mission_id)
    black = runtime.route(ActionRequest("sign_contract", "sign", 3, 1, 10), contract.mission_id)
    assert red.governor.mode == Autonomy.BLOCK
    assert black.governor.mode == Autonomy.BLOCK
    assert runtime.store.pending_approvals() == ()
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_unknown_mission_fails_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    result = runtime.route(ActionRequest("safe_action", "safe", 1, 1, 10), "MIS-DOES-NOT-EXIST")
    assert result.governor.mode == Autonomy.BLOCK
    assert result.allowed is False
    assert runtime.store.pending_approvals() == ()


def test_mismatched_action_contract_fails_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared")
    action = ActionRequest("safe_action", "safe", 1, 1, 10, contract_id="MIS-WRONG")
    result = runtime.route(action, contract.mission_id)
    assert result.governor.mode == Autonomy.BLOCK
    assert result.allowed is False
    assert runtime.store.pending_approvals() == ()
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_action_is_bound_to_mission_contract(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared")
    action = ActionRequest("safe_action", "safe", 1, 1, 10)
    result = runtime.route(action, contract.mission_id)
    assert result.action.contract_id == contract.mission_id
    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED


def test_illegal_mission_transition_is_rejected(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("career", "application prepared")
    with pytest.raises(ValueError, match="Transition de mission interdite"):
        runtime._set_status(contract.mission_id, MissionStatus.COMPLETED)
