import pytest

from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.effects import EffectRequest, ExternalEffectCoordinator


class Provider:
    def __init__(self):
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        raise AssertionError("execute must not be called")

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        raise AssertionError("reconcile must not be called")


def _store(tmp_path, status):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-REC", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-REC'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-rec", "MIS-REC", "ACT-1", status),
        )
    return store


def _request():
    return EffectRequest("exec-rec", "provider", "write", {"value": 1}, "action-fp")


def test_reconcile_requires_recovery_execution(tmp_path):
    store = _store(tmp_path, "RUNNING")
    coordinator = ExternalEffectCoordinator(store)
    provider = Provider()

    with pytest.raises(RuntimeError, match="RECOVERY_REQUIRED"):
        coordinator.reconcile(_request(), provider)

    assert provider.reconcile_calls == 0


def test_reconcile_requires_persisted_effect(tmp_path):
    store = _store(tmp_path, "RECOVERY_REQUIRED")
    coordinator = ExternalEffectCoordinator(store)
    provider = Provider()

    with pytest.raises(RuntimeError, match="preuve durable"):
        coordinator.reconcile(_request(), provider)

    assert provider.reconcile_calls == 0
