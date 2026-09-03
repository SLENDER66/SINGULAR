"""Adversarial recovery tests.

External reconciliation proves the remote effect, but it is not itself the
execution-state finalizer. Keeping these authorities separate prevents a
provider adapter from silently rewriting mission lifecycle state.
"""

from singular.autopilot import DelegationContract
from singular.durable import DurableStore, MissionStatus
from singular.effects import EffectRequest, ExternalEffectCoordinator, ProviderResult


class RecoverableProvider:
    def execute(self, request, idempotency_key):
        return ProviderResult("UNKNOWN", error="network ambiguity")

    def reconcile(self, request, idempotency_key):
        return ProviderResult("COMPLETED", {"remote_id": "confirmed"})


def test_external_reconciliation_does_not_bypass_execution_finalizer(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(
        DelegationContract(
            mission_id="MIS-RECOVERY",
            objective="recover",
            expected_result="completed",
        )
    )
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-RECOVERY'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-recovery", "MIS-RECOVERY", "ACT-1", "RECOVERY_REQUIRED"),
        )

    coordinator = ExternalEffectCoordinator(store)
    request = EffectRequest(
        execution_key="exec-recovery",
        provider="recoverable",
        operation="confirm",
        payload={"id": "x"},
        action_fingerprint="action-fingerprint",
    )
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO external_effects(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,action_fingerprint,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                request.provider_idempotency_key,
                request.execution_key,
                request.provider,
                request.operation,
                request.payload_fingerprint,
                request.action_fingerprint,
                "UNKNOWN",
                "now",
                "now",
            ),
        )

    outcome = coordinator.reconcile(request, RecoverableProvider())
    assert outcome.status == "COMPLETED"
    execution = store.get_execution("exec-recovery")
    assert execution is not None
    assert execution["status"] == "RECOVERY_REQUIRED"
    assert store.get_mission_status("MIS-RECOVERY") is MissionStatus.RUNNING
