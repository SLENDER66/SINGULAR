from pathlib import Path

import pytest

from singular.durable import DurableStore
from singular.effects import (
    EffectRequest,
    EffectStatus,
    ExternalEffectCoordinator,
    ProviderResult,
)
from tests.support import claimed_execution_store


class FakeProvider:
    def __init__(self):
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        return ProviderResult("COMPLETED", {"ok": True})

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return ProviderResult("COMPLETED", {"reconciled": True})


def make_request(store: DurableStore) -> tuple[ExternalEffectCoordinator, EffectRequest]:
    coordinator = ExternalEffectCoordinator(store)
    request = EffectRequest("execution-1", "fake", "send", {"to": "a"}, "action-fp")
    return coordinator, request


def test_concurrent_transition_can_only_finalize_once(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    coordinator, request = make_request(store)
    coordinator.prepare(request)
    assert coordinator._claim(request.provider_idempotency_key) is True
    coordinator._transition(request.provider_idempotency_key, EffectStatus.COMPLETED.value, result={"ok": True})

    with pytest.raises(RuntimeError, match="Transition d'effet perdue|concurrence d'état"):
        coordinator._transition(request.provider_idempotency_key, EffectStatus.UNKNOWN.value, error="late worker")

    assert coordinator.get(request)["status"] == EffectStatus.COMPLETED.value


def test_recovery_race_cannot_recover_completed_effect(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    coordinator, request = make_request(store)
    coordinator.prepare(request)
    assert coordinator._claim(request.provider_idempotency_key) is True
    coordinator._transition(request.provider_idempotency_key, EffectStatus.COMPLETED.value, result={"ok": True})

    with pytest.raises(ValueError, match="Récupération d'effet impossible"):
        coordinator.recover_in_flight(request, reason="worker supposé abandonné")

    assert coordinator.get(request)["status"] == EffectStatus.COMPLETED.value


def test_unknown_reconciliation_is_idempotent_after_completion(tmp_path: Path):
    store = claimed_execution_store(tmp_path / "s.db", execution_key="execution-1")
    coordinator, request = make_request(store)
    coordinator.prepare(request)
    assert coordinator._claim(request.provider_idempotency_key) is True
    coordinator._transition(request.provider_idempotency_key, EffectStatus.UNKNOWN.value, error="ambiguous")
    # Reconciliation is reserved to quarantined executions.
    store.mark_execution_recovery_required("execution-1")

    provider = FakeProvider()
    first = coordinator.reconcile(request, provider)
    second = coordinator.reconcile(request, provider)

    assert first.status == EffectStatus.COMPLETED.value
    assert second.status == EffectStatus.COMPLETED.value
    assert provider.reconcile_calls == 1
