from pathlib import Path

import pytest

from singular.effects import (
    EffectRequest,
    EffectStatus,
    ExternalEffectCoordinator,
    ProviderResult,
)
from tests.support import claimed_execution_store


class Provider:
    def __init__(self):
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        self.execute_calls += 1
        return ProviderResult("COMPLETED", {"ok": True})

    def reconcile(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        self.reconcile_calls += 1
        return ProviderResult("COMPLETED", {"reconciled": True})


def make_request() -> EffectRequest:
    return EffectRequest(
        execution_key="execution-1",
        provider="fake",
        operation="send",
        payload={"to": "a@example.com"},
        action_fingerprint="action-1",
    )


def test_abandoned_in_flight_claim_requires_explicit_recovery(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_execution_store(tmp_path / "effects.db", execution_key="execution-1"))
    provider = Provider()
    request = make_request()
    coordinator.prepare(request)

    with coordinator._connect() as conn:
        conn.execute(
            "UPDATE external_effects SET status=? WHERE provider_idempotency_key=?",
            (EffectStatus.IN_FLIGHT.value, request.provider_idempotency_key),
        )

    with pytest.raises(ValueError, match="raison"):
        coordinator.recover_in_flight(request, reason="")
    with pytest.raises(Exception):
        coordinator.execute(request, provider)
    assert provider.execute_calls == 0

    recovered = coordinator.recover_in_flight(request, reason="worker crash confirmed")
    assert recovered["status"] == EffectStatus.UNKNOWN.value
    assert provider.execute_calls == 0

    with pytest.raises(RuntimeError, match="réconciliation explicite"):
        coordinator.execute(request, provider)
    assert provider.execute_calls == 0

    # Reconciliation is reserved to quarantined executions; the engine marks the
    # execution when a provider outcome comes back UNKNOWN.
    coordinator.store.mark_execution_recovery_required(request.execution_key)
    result = coordinator.reconcile(request, provider)
    assert result.status == EffectStatus.COMPLETED.value
    assert provider.execute_calls == 0
    assert provider.reconcile_calls == 1


def test_recovery_cannot_be_used_to_reopen_completed_or_failed_effect(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_execution_store(tmp_path / "effects.db", execution_key="execution-1"))
    provider = Provider()
    request = make_request()

    coordinator.execute(request, provider)
    with pytest.raises(ValueError, match="COMPLETED"):
        coordinator.recover_in_flight(request, reason="invalid recovery")
    assert provider.execute_calls == 1
