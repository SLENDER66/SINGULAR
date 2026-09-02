from pathlib import Path

import pytest

from singular.durable import DurableStore
from singular.effects import EffectInProgress, EffectRequest, EffectStatus, ExternalEffectCoordinator, ProviderResult


class FakeProvider:
    def __init__(self, outcome: ProviderResult | None = None, error: Exception | None = None):
        self.outcome = outcome or ProviderResult("COMPLETED", {"provider_id": "1"})
        self.error = error
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        self.execute_calls += 1
        if self.error:
            raise self.error
        return self.outcome

    def reconcile(self, request: EffectRequest, idempotency_key: str) -> ProviderResult:
        self.reconcile_calls += 1
        return self.outcome


def request(**overrides) -> EffectRequest:
    values = {
        "execution_key": "execute-key",
        "provider": "fake-mail",
        "operation": "send",
        "payload": {"to": "a@example.com", "body": "hello"},
        "action_fingerprint": "action-fp-1",
    }
    values.update(overrides)
    return EffectRequest(**values)


def test_provider_key_is_stable_and_payload_is_bound_separately():
    first = request()
    second = request()
    changed = request(payload={"body": "changed"})
    assert first.provider_idempotency_key == second.provider_idempotency_key
    assert first.provider_idempotency_key == changed.provider_idempotency_key
    assert first.payload_fingerprint != changed.payload_fingerprint


def test_completed_effect_is_not_sent_twice(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(DurableStore(tmp_path / "effects.db"))
    provider = FakeProvider()
    assert coordinator.execute(request(), provider).status == "COMPLETED"
    assert coordinator.execute(request(), provider).status == "COMPLETED"
    assert provider.execute_calls == 1


def test_provider_error_becomes_unknown_and_requires_reconciliation(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(DurableStore(tmp_path / "effects.db"))
    provider = FakeProvider(error=TimeoutError("response lost"))
    result = coordinator.execute(request(), provider)
    assert result.status == "UNKNOWN"
    assert coordinator.get(request())["status"] == EffectStatus.UNKNOWN.value

    with pytest.raises(RuntimeError, match="réconciliation explicite"):
        coordinator.execute(request(), provider)
    assert provider.execute_calls == 1


def test_reconciliation_confirms_unknown_without_reexecution(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(DurableStore(tmp_path / "effects.db"))
    provider = FakeProvider(error=TimeoutError("response lost"))
    coordinator.execute(request(), provider)
    provider.error = None
    provider.outcome = ProviderResult("COMPLETED", {"provider_id": "confirmed"})

    result = coordinator.reconcile(request(), provider)
    assert result.status == "COMPLETED"
    assert result.result == {"provider_id": "confirmed"}
    assert provider.execute_calls == 1
    assert provider.reconcile_calls == 1


def test_same_provider_key_cannot_change_payload(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(DurableStore(tmp_path / "effects.db"))
    original = request()
    coordinator.prepare(original)
    forged = request(payload={"to": "attacker@example.com"})
    with pytest.raises(ValueError, match="payload différent"):
        coordinator.prepare(forged)


def test_same_provider_key_cannot_change_action_identity(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(DurableStore(tmp_path / "effects.db"))
    original = request()
    coordinator.prepare(original)
    forged = request(action_fingerprint="forged-action")
    with pytest.raises(ValueError, match="identité d'action différente"):
        coordinator.prepare(forged)


def test_in_flight_effect_has_single_claimant(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(DurableStore(tmp_path / "effects.db"))
    provider = FakeProvider()
    original = request()
    coordinator.prepare(original)
    key = original.provider_idempotency_key
    with coordinator._connect() as conn:
        conn.execute("UPDATE external_effects SET status=? WHERE provider_idempotency_key=?", (EffectStatus.IN_FLIGHT.value, key))

    with pytest.raises(EffectInProgress):
        coordinator.execute(original, provider)
    assert provider.execute_calls == 0
