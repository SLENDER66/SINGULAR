from pathlib import Path

from singular.autopilot import ActionRequest, ApprovalStatus, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.mission_runtime import DurableMissionRuntime


def test_mission_survives_runtime_restart(tmp_path: Path):
    db = tmp_path / "singular.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("emploi et revenus", "plan concret", autonomy=Autonomy.PREPARE)

    second = DurableMissionRuntime(DurableStore(db))
    assert second.store.load_mission(contract.mission_id).objective == "emploi et revenus"
    assert second.state(contract.mission_id).status == MissionStatus.CREATED


def test_pending_approval_survives_runtime_restart_and_can_be_resolved(tmp_path: Path):
    db = tmp_path / "singular.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    first.route(ActionRequest("send_application", "send", 5, 6, 6), contract.mission_id)
    approval = first.store.pending_approvals(contract.mission_id)[0]

    second = DurableMissionRuntime(DurableStore(db))
    assert second.state(contract.mission_id).status == MissionStatus.WAITING_APPROVAL
    recovered = second.store.pending_approvals(contract.mission_id)
    assert len(recovered) == 1
    assert recovered[0].id == approval.id
    assert recovered[0].status == ApprovalStatus.PENDING

    second.approve(approval.id)
    assert second.store.pending_approvals(contract.mission_id) == ()
    assert second.state(contract.mission_id).status == MissionStatus.PLANNED


def test_missions_have_unique_ids(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    first = runtime.create_mission("same objective", "same result")
    second = runtime.create_mission("same objective", "same result")
    assert first.mission_id != second.mission_id


def test_sensitive_action_creates_no_execution_and_is_blocked(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("finance", "préparer", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    result = runtime.route(ActionRequest("transfer_money", "transfer", 9, 9, 1), contract.mission_id)
    assert not result.allowed
    assert result.governor.mode == Autonomy.BLOCK
    assert runtime.store.pending_approvals() == ()
    assert runtime.state(contract.mission_id).status == MissionStatus.BLOCKED


def test_idempotency_key_is_deterministic(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    key1 = store.idempotency_key("mission", "action", "v1")
    key2 = store.idempotency_key("mission", "action", "v1")
    assert key1 == key2
    assert len(key1) == 64
