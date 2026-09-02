from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.effects import ExternalEffectCoordinator, ProviderResult
from singular.execution import DurableExecutionEngine, ExecutionRecoveryRequired
from singular.mission_runtime import DurableMissionRuntime


class FakeProvider:
    def __init__(self, outcome: ProviderResult | None = None, error: Exception | None = None):
        self.outcome = outcome or ProviderResult("COMPLETED", {"provider_id": "1"})
        self.error = error
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        if self.error:
            raise self.error
        return self.outcome

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return self.outcome


def setup(tmp_path: Path, *, autonomy: Autonomy = Autonomy.EXECUTE_REVERSIBLE):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("external effect", "provider operation completed", autonomy=autonomy)
    coordinator = ExternalEffectCoordinator(runtime.store)
    engine = DurableExecutionEngine(runtime, effect_coordinator=coordinator)
    return runtime, contract, engine


def test_external_effect_executes_once_and_is_durable(tmp_path: Path):
    runtime, contract, engine = setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    provider = FakeProvider()

    first = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert first.status == "COMPLETED"
    assert first.result == {"provider_id": "1"}
    assert provider.execute_calls == 1
    assert runtime.state(contract.mission_id).status == MissionStatus.COMPLETED


def test_external_timeout_quarantines_execution_and_never_retries(tmp_path: Path):
    runtime, contract, engine = setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    provider = FakeProvider(error=TimeoutError("response lost"))

    first = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert first.status == "RECOVERY_REQUIRED"
    assert runtime.state(contract.mission_id).status == MissionStatus.RUNNING
    assert provider.execute_calls == 1

    with pytest.raises(ExecutionRecoveryRequired):
        engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})
    assert provider.execute_calls == 1


def test_reconciliation_confirms_without_provider_reexecution(tmp_path: Path):
    runtime, contract, engine = setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    provider = FakeProvider(error=TimeoutError("response lost"))

    first = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})
    assert first.status == "RECOVERY_REQUIRED"

    provider.error = None
    provider.outcome = ProviderResult("COMPLETED", {"provider_id": "confirmed"})
    result = engine.reconcile_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert result.status == "COMPLETED"
    assert result.result == {"provider_id": "confirmed"}
    assert provider.execute_calls == 1
    assert provider.reconcile_calls == 1
    assert runtime.state(contract.mission_id).status == MissionStatus.COMPLETED


def test_effect_payload_tampering_is_rejected_before_reconciliation(tmp_path: Path):
    runtime, contract, engine = setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    provider = FakeProvider(error=TimeoutError("response lost"))

    engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "original"})
    provider.error = None
    provider.outcome = ProviderResult("COMPLETED", {"provider_id": "confirmed"})

    with pytest.raises(ValueError, match="payload différent"):
        engine.reconcile_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "attacker"})
    assert provider.reconcile_calls == 0


def test_sensitive_effect_still_requires_human_approval(tmp_path: Path):
    runtime, contract, engine = setup(tmp_path, autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    provider = FakeProvider()

    with pytest.raises(PermissionError, match="approbation humaine"):
        engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert provider.execute_calls == 0
    assert runtime.state(contract.mission_id).status == MissionStatus.WAITING_APPROVAL

    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)
    result = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert result.status == "COMPLETED"
    assert provider.execute_calls == 1


def test_tampered_native_approval_binding_is_refused_before_provider_call(tmp_path: Path):
    runtime, contract, engine = setup(tmp_path, autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)
    provider = FakeProvider()

    with pytest.raises(PermissionError):
        engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    runtime.route(action, contract.mission_id)
    approval = runtime.store.pending_approvals(contract.mission_id)[0]
    runtime.approve(approval.id)

    with runtime.store._connect() as conn:
        conn.execute(
            "UPDATE approval_bindings SET action_fingerprint=? WHERE approval_id=?",
            ("TAMPERED", approval.id),
        )

    with pytest.raises(PermissionError, match="action ou son contexte a changé"):
        engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert provider.execute_calls == 0
    assert runtime.state(contract.mission_id).status == MissionStatus.PLANNED
