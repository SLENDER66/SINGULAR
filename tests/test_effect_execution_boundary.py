import pytest

from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.effects import EffectRequest, ExternalEffectCoordinator, ProviderResult


class CountingProvider:
    def __init__(self):
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        return ProviderResult("COMPLETED", {"ok": True})

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return ProviderResult("COMPLETED", {"remote": True})


def _store_with_execution(tmp_path, status):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(
        DelegationContract(
            mission_id="MIS-EFFECT-BOUNDARY",
            objective="test",
            expected_result="done",
        )
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-EFFECT-BOUNDARY'"
        )
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-boundary", "MIS-EFFECT-BOUNDARY", "ACT-1", status),
        )
    return store


def _request():
    return EffectRequest(
        execution_key="exec-boundary",
        provider="provider",
        operation="write",
        payload={"value": 1},
        action_fingerprint="action-fp",
    )


def test_recovery_required_execution_cannot_reexecute_external_effect(tmp_path):
    store = _store_with_execution(tmp_path, "RECOVERY_REQUIRED")
    coordinator = ExternalEffectCoordinator(store)
    provider = CountingProvider()

    with pytest.raises(RuntimeError, match="réconciliation explicite"):
        coordinator.execute(_request(), provider)

    assert provider.execute_calls == 0


def test_completed_execution_cannot_reexecute_external_effect(tmp_path):
    store = _store_with_execution(tmp_path, "COMPLETED")
    coordinator = ExternalEffectCoordinator(store)
    provider = CountingProvider()

    with pytest.raises(RuntimeError, match="état COMPLETED"):
        coordinator.execute(_request(), provider)

    assert provider.execute_calls == 0


def test_missing_execution_cannot_create_external_effect(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    coordinator = ExternalEffectCoordinator(store)
    provider = CountingProvider()

    with pytest.raises(KeyError):
        coordinator.execute(_request(), provider)

    assert provider.execute_calls == 0


def test_running_execution_cannot_reconcile_external_effect(tmp_path):
    store = _store_with_execution(tmp_path, "RUNNING")
    coordinator = ExternalEffectCoordinator(store)
    request = _request()
    coordinator.prepare(request)
    provider = CountingProvider()

    with pytest.raises(RuntimeError, match="RECOVERY_REQUIRED"):
        coordinator.reconcile(request, provider)

    assert provider.reconcile_calls == 0
