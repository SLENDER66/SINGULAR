from pathlib import Path

from singular.autopilot import ActionRequest, Autonomy, ApprovalStatus
from singular.durable import DurableStore
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

    runtime.approve(pending[0].id)
    assert runtime.store.pending_approvals() == ()


def test_red_and_black_actions_fail_closed(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("finance", "safe plan", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    red = runtime.route(ActionRequest("high_risk", "danger", 8, 8, 6), contract.mission_id)
    black = runtime.route(ActionRequest("sign_contract", "sign", 3, 1, 10), contract.mission_id)
    assert red.governor.mode == Autonomy.BLOCK
    assert black.governor.mode == Autonomy.BLOCK
    assert runtime.store.pending_approvals() == ()
