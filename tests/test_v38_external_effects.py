from pathlib import Path

import pytest

from singular.autopilot import Autonomy, DelegationContract
from singular.durable import DurableStore, MissionStatus
from singular.effects import (
    EffectInProgress,
    EffectRequest,
    EffectStatus,
    ExternalEffectCoordinator,
    ProviderResult,
)

MISSION_ID = "MIS-EFFECT"
EXECUTION_KEY = "execute-key"


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


def claimed_store(tmp_path: Path) -> DurableStore:
    """An external effect is only permitted under a claimed durable execution.

    ExternalEffectCoordinator refuses a request whose execution_key owns no
    RUNNING execution row: an effect nobody claimed could be produced by any
    caller, outside the lease that makes it exactly-once. These tests used to
    invent an execution key with no execution behind it, so they exercised the
    coordinator with the ownership check unsatisfied.
    """
    store = DurableStore(tmp_path / "effects.db")
    store.save_mission(DelegationContract(MISSION_ID, "objective", "expected", autonomy=Autonomy.EXECUTE_REVERSIBLE))
    store.init_execution_schema()
    store.set_mission_status(MISSION_ID, MissionStatus.PLANNED)
    store.begin_execution_and_start_mission(EXECUTION_KEY, MISSION_ID, "ACT-EFFECT", lease_seconds=300)
    return store


def request(**overrides) -> EffectRequest:
    values = {
        "execution_key": EXECUTION_KEY,
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
    coordinator = ExternalEffectCoordinator(claimed_store(tmp_path))
    provider = FakeProvider()
    assert coordinator.execute(request(), provider).status == "COMPLETED"
    assert coordinator.execute(request(), provider).status == "COMPLETED"
    assert provider.execute_calls == 1


def test_provider_error_becomes_unknown_and_requires_reconciliation(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_store(tmp_path))
    provider = FakeProvider(error=TimeoutError("response lost"))
    result = coordinator.execute(request(), provider)
    assert result.status == "UNKNOWN"
    assert coordinator.get(request())["status"] == EffectStatus.UNKNOWN.value

    with pytest.raises(RuntimeError, match="réconciliation explicite"):
        coordinator.execute(request(), provider)
    assert provider.execute_calls == 1


def test_reconciliation_confirms_unknown_without_reexecution(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_store(tmp_path))
    provider = FakeProvider(error=TimeoutError("response lost"))
    coordinator.execute(request(), provider)
    provider.error = None
    provider.outcome = ProviderResult("COMPLETED", {"provider_id": "confirmed"})
    # Reconciliation is reserved to quarantined executions; the engine marks
    # this when a provider outcome comes back UNKNOWN.
    coordinator.store.mark_execution_recovery_required(EXECUTION_KEY)

    result = coordinator.reconcile(request(), provider)
    assert result.status == "COMPLETED"
    assert result.result == {"provider_id": "confirmed"}
    assert provider.execute_calls == 1
    assert provider.reconcile_calls == 1


def test_same_provider_key_cannot_change_payload(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_store(tmp_path))
    original = request()
    coordinator.prepare(original)
    forged = request(payload={"to": "attacker@example.com"})
    with pytest.raises(ValueError, match="payload différent"):
        coordinator.prepare(forged)


def test_same_provider_key_cannot_change_action_identity(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_store(tmp_path))
    original = request()
    coordinator.prepare(original)
    forged = request(action_fingerprint="forged-action")
    with pytest.raises(ValueError, match="identité d'action différente"):
        coordinator.prepare(forged)


def test_in_flight_effect_has_single_claimant(tmp_path: Path):
    coordinator = ExternalEffectCoordinator(claimed_store(tmp_path))
    provider = FakeProvider()
    original = request()
    coordinator.prepare(original)
    key = original.provider_idempotency_key
    with coordinator._connect() as conn:
        conn.execute("UPDATE external_effects SET status=? WHERE provider_idempotency_key=?", (EffectStatus.IN_FLIGHT.value, key))

    with pytest.raises(EffectInProgress):
        coordinator.execute(original, provider)
    assert provider.execute_calls == 0
