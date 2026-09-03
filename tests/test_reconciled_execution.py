from singular.autopilot import DelegationContract
from singular.durable import DurableStore, MissionStatus
from singular.effects import EffectRequest, EffectStatus, ExternalEffectCoordinator, ProviderResult
from singular.reconciled_execution import ReconciledExecutionFinalizer


class Provider:
    def execute(self, request, idempotency_key):
        return ProviderResult(EffectStatus.UNKNOWN.value, error="network ambiguity")

    def reconcile(self, request, idempotency_key):
        return ProviderResult(EffectStatus.COMPLETED.value, {"remote_id": "confirmed"})


def _setup(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract("MIS-1", "recover", "done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-1'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("EXEC-1", "MIS-1", "ACT-1", "RECOVERY_REQUIRED"),
        )
    request = EffectRequest("EXEC-1", "provider", "send", {"id": "x"}, "action-fp")
    coordinator = ExternalEffectCoordinator(store)
    return store, request, coordinator


def test_reconciliation_proves_effect_then_finalizer_closes_execution(tmp_path):
    store, request, coordinator = _setup(tmp_path)
    outcome = coordinator.execute(request, Provider())
    assert outcome.status == EffectStatus.UNKNOWN.value

    outcome = coordinator.reconcile(request, Provider())
    assert outcome.status == EffectStatus.COMPLETED.value
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"

    final = ReconciledExecutionFinalizer(store).finalize(
        "EXEC-1",
        provider=request.provider,
        operation=request.operation,
        payload_fingerprint=request.payload_fingerprint,
        action_fingerprint=request.action_fingerprint,
    )
    assert final.result == {"remote_id": "confirmed"}
    assert store.get_execution("EXEC-1")["status"] == "COMPLETED"
    assert store.get_mission_status("MIS-1") is MissionStatus.COMPLETED


def test_finalizer_rejects_operator_asserted_success_without_completed_effect(tmp_path):
    store, request, _ = _setup(tmp_path)
    try:
        ReconciledExecutionFinalizer(store).finalize(
            "EXEC-1",
            provider=request.provider,
            operation=request.operation,
            payload_fingerprint=request.payload_fingerprint,
            action_fingerprint=request.action_fingerprint,
        )
    except ValueError as exc:
        assert "preuve durable" in str(exc)
    else:
        raise AssertionError("Unauthenticated recovery finalization was accepted")
    assert store.get_execution("EXEC-1")["status"] == "RECOVERY_REQUIRED"


def test_finalizer_rejects_payload_substitution(tmp_path):
    store, request, coordinator = _setup(tmp_path)
    coordinator.prepare(request)
    with store._connect() as conn:
        conn.execute(
            "UPDATE external_effects SET status='COMPLETED',result=? WHERE provider_idempotency_key=?",
            ('{"ok":true}', request.provider_idempotency_key),
        )
    try:
        ReconciledExecutionFinalizer(store).finalize(
            "EXEC-1",
            provider=request.provider,
            operation=request.operation,
            payload_fingerprint="forged-payload-fingerprint",
            action_fingerprint=request.action_fingerprint,
        )
    except ValueError as exc:
        assert "payload" in str(exc)
    else:
        raise AssertionError("Payload substitution was accepted")
