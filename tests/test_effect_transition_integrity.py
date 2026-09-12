from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.effects import EffectRequest, EffectStatus, ExternalEffectCoordinator


def test_duplicate_terminal_transition_does_not_erase_result(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-TRANSITION", "test", "done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-TRANSITION'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-transition", "MIS-TRANSITION", "ACT-1", "RUNNING"),
        )
    coordinator = ExternalEffectCoordinator(store)
    request = EffectRequest("exec-transition", "provider", "write", {"value": 1}, "action-fp")
    coordinator.prepare(request)
    key = request.provider_idempotency_key
    coordinator._claim(key)
    coordinator._transition(key, EffectStatus.COMPLETED.value, result={"remote_id": "42"})
    coordinator._transition(key, EffectStatus.COMPLETED.value)

    persisted = coordinator.peek(request)
    assert persisted["status"] == EffectStatus.COMPLETED.value
    assert persisted["result"] == {"remote_id": "42"}
