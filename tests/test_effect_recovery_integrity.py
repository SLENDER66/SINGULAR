import pytest

from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.effects import EffectRequest, ExternalEffectCoordinator


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-RECOVERY", "test", "done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-RECOVERY'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-recovery", "MIS-RECOVERY", "ACT-1", "RECOVERY_REQUIRED"),
        )
    return store


def _request():
    return EffectRequest("exec-recovery", "provider", "write", {"value": 1}, "action-fp")


def test_reconciliation_cannot_create_missing_effect_intent(tmp_path):
    store = _store(tmp_path)
    coordinator = ExternalEffectCoordinator(store)

    class Provider:
        def reconcile(self, request, idempotency_key):
            raise AssertionError("provider must not be called without persisted effect evidence")

    with pytest.raises(RuntimeError, match="Aucune preuve durable"):
        coordinator.reconcile(_request(), Provider())

    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM external_effects").fetchone()[0] == 0


def test_recovery_of_missing_effect_does_not_create_intent(tmp_path):
    store = _store(tmp_path)
    coordinator = ExternalEffectCoordinator(store)

    with pytest.raises(KeyError):
        coordinator.recover_in_flight(_request(), reason="worker crashed")

    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM external_effects").fetchone()[0] == 0
