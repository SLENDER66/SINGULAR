from pathlib import Path

import pytest

from singular.autopilot import ActionRequest
from singular.durable import DurableStore, MissionStatus
from singular.effects import EffectRequest, ExternalEffectCoordinator, ProviderResult
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime


class FakeProvider:
    def __init__(self, outcome: ProviderResult):
        self.outcome = outcome
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        return self.outcome

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return self.outcome


def setup(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("external effect", "provider outcome")
    coordinator = ExternalEffectCoordinator(runtime.store)
    engine = DurableExecutionEngine(runtime, effect_coordinator=coordinator)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    return runtime, contract, engine, coordinator, action


def reset_to_running(store: DurableStore, mission_id: str, execution_key: str) -> None:
    with store._connect() as conn:
        conn.execute("UPDATE executions SET status='RUNNING', error=NULL, result=NULL WHERE execution_key=?", (execution_key,))
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id=?", (mission_id,))


def test_completed_external_effect_repairs_running_execution_without_reexecution(tmp_path: Path):
    runtime, contract, engine, coordinator, action = setup(tmp_path)
    provider = FakeProvider(ProviderResult("COMPLETED", {"provider_id": "one"}))

    first = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})
    assert first.status == "COMPLETED"
    assert provider.execute_calls == 1

    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    reset_to_running(runtime.store, contract.mission_id, key)

    replay = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert replay.status == "COMPLETED"
    assert replay.result == {"provider_id": "one"}
    assert provider.execute_calls == 1
    assert runtime.state(contract.mission_id).status == MissionStatus.COMPLETED
    assert runtime.store.get_execution(key)["status"] == "COMPLETED"


def test_failed_external_effect_repairs_running_execution_without_reexecution(tmp_path: Path):
    runtime, contract, engine, coordinator, action = setup(tmp_path)
    provider = FakeProvider(ProviderResult("FAILED", error="provider rejected"))

    first = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})
    assert first.status == "FAILED"
    assert provider.execute_calls == 1

    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    reset_to_running(runtime.store, contract.mission_id, key)

    replay = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert replay.status == "FAILED"
    assert replay.error == "provider rejected"
    assert provider.execute_calls == 1
    assert runtime.state(contract.mission_id).status == MissionStatus.FAILED


def test_unknown_external_effect_quarantines_running_execution_without_reexecution(tmp_path: Path):
    runtime, contract, engine, coordinator, action = setup(tmp_path)
    provider = FakeProvider(ProviderResult("UNKNOWN", error="ambiguous"))

    first = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})
    assert first.status == "RECOVERY_REQUIRED"
    assert provider.execute_calls == 1

    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    reset_to_running(runtime.store, contract.mission_id, key)

    replay = engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})

    assert replay.status == "RECOVERY_REQUIRED"
    assert replay.error == "ambiguous"
    assert provider.execute_calls == 1
    assert runtime.store.get_execution(key)["status"] == "RECOVERY_REQUIRED"


def test_peek_does_not_create_missing_effect_intent(tmp_path: Path):
    runtime, contract, engine, coordinator, action = setup(tmp_path)
    key = runtime.store.idempotency_key("execute", contract.mission_id, action.id)
    request = EffectRequest(
        execution_key=key,
        provider="fake",
        operation="send",
        payload={"to": "a"},
        action_fingerprint=runtime._action_fingerprint(action, contract.mission_id),
    )

    with pytest.raises(KeyError):
        coordinator.peek(request)

    with runtime.store._connect() as conn:
        row = conn.execute("SELECT * FROM external_effects WHERE provider_idempotency_key=?", (request.provider_idempotency_key,)).fetchone()
    assert row is None
