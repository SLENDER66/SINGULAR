from pathlib import Path

from singular.autopilot import ActionRequest, ApprovalStatus, Autonomy
from singular.durable import DurableStore
from singular.mission_runtime import DurableMissionRuntime


def test_mission_survives_runtime_restart(tmp_path: Path):
    db = tmp_path / "singular.db"
    first = DurableMissionRuntime(DurableStore(db))
    contract = first.create_mission("emploi et revenus", "plan concret", autonomy=Autonomy.PREPARE)

    second = DurableMissionRuntime(DurableStore(db))
    assert second.store.load_mission(contract.mission_id).objective == "emploi et revenus"


def test_sensitive_action_creates_no_execution_and_is_blocked(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("finance", "préparer", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    result = runtime.route(ActionRequest("transfer_money", "transfer", 9, 9, 1), contract.mission_id)
    assert not result.allowed
    assert result.governor.mode == Autonomy.BLOCK
    assert runtime.store.pending_approvals() == ()


def test_idempotency_key_is_deterministic(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    key1 = store.idempotency_key("mission", "action", "v1")
    key2 = store.idempotency_key("mission", "action", "v1")
    assert key1 == key2
    assert len(key1) == 64
