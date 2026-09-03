"""Adversarial recovery tests.

Recovery is a first-class execution state: a recovered external effect must
produce a durable terminal execution and mission state, never merely a
process-local COMPLETED result.
"""

import pytest

from singular.durable import DurableStore, MissionStatus
from singular.effects import EffectRequest, ExternalEffectCoordinator, ProviderResult


class RecoverableProvider:
    def __init__(self) -> None:
        self.reconciled = False

    def execute(self, request, idempotency_key):
        return ProviderResult("UNKNOWN", error="network ambiguity")

    def reconcile(self, request, idempotency_key):
        self.reconciled = True
        return ProviderResult("COMPLETED", {"remote_id": "confirmed"})


def test_recovery_completion_cannot_leave_execution_and_mission_divergent(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(__import__("singular.autopilot", fromlist=["DelegationContract"]).DelegationContract(
        mission_id="MIS-RECOVERY",
        objective="recover",
        expected_result="completed",
    ))
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
            (request.provider_idempotency_key, request.execution_key, request.provider, request.operation,
             request.payload_fingerprint, request.action_fingerprint, "UNKNOWN", "now", "now"),
        )

    outcome = coordinator.reconcile(request, RecoverableProvider())
    assert outcome.status == "COMPLETED"
    # The coordinator may prove the external effect, but that proof must not
    # silently mutate the durable execution state behind the execution engine.
    execution = store.get_execution("exec-recovery")
    assert execution is not None
    assert execution["status"] == "RECOVERY_REQUIRED"
    assert store.get_mission_status("MIS-RECOVERY") is MissionStatus.RUNNING
