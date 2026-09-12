from pathlib import Path

from singular.durable import DurableStore
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


def test_execution_recovery_clears_lease(tmp_path: Path):
    store = DurableStore(tmp_path / "recovery.db")
    contract = __import__("singular.autopilot", fromlist=["DelegationContract"]).DelegationContract(
        mission_id="m1",
        objective="objective",
        expected_result="result",
        autonomy=__import__("singular.autopilot", fromlist=["Autonomy"]).Autonomy.EXECUTE_REVERSIBLE,
        budget_limit=0,
        deadline=None,
        forbidden_actions=(),
        escalation_conditions=(),
        success_criteria=(),
    )
    store.save_mission(contract)
    store.set_mission_status("m1", "PLANNED")
    claimed = store.begin_execution_and_start_mission("e1", "m1", "a1", lease_seconds=1)
    assert claimed["status"] == "RUNNING"

    with store._connect() as conn:
        conn.execute("UPDATE executions SET lease_until=? WHERE execution_key=?", ("2000-01-01T00:00:00+00:00", "e1"))

    recovered = store.recover_stale_execution("e1")
    assert recovered is not None
    assert recovered["status"] == "RECOVERY_REQUIRED"
    assert recovered["lease_until"] is None


def test_effect_recovery_and_execution_recovery_cannot_reexecute_provider(tmp_path: Path):
    # The coordinator only serves an execution that owns a RUNNING row, and only
    # reconciles a quarantined one: an effect nobody claimed is outside the lease
    # that makes it exactly-once.
    store = claimed_execution_store(tmp_path / "effect-recovery.db", execution_key="e1")
    coordinator = ExternalEffectCoordinator(store)
    provider = Provider()
    request = EffectRequest("e1", "fake", "send", {"to": "a"}, "action-1")

    coordinator.prepare(request)
    with coordinator._connect() as conn:
        conn.execute(
            "UPDATE external_effects SET status=? WHERE provider_idempotency_key=?",
            (EffectStatus.IN_FLIGHT.value, request.provider_idempotency_key),
        )

    recovered = coordinator.recover_in_flight(request, reason="worker crash confirmed")
    assert recovered["status"] == EffectStatus.UNKNOWN.value
    assert provider.execute_calls == 0

    store.mark_execution_recovery_required("e1")
    result = coordinator.reconcile(request, provider)
    assert result.status == EffectStatus.COMPLETED.value
    assert provider.execute_calls == 0
    assert provider.reconcile_calls == 1
