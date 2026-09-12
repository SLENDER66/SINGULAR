from types import SimpleNamespace

from singular.effects import EffectRequest, EffectStatus
from singular.execution import DurableExecutionEngine


class FakeStore:
    def __init__(self, status):
        self.status = status
        self.confirm_calls = []
        self.fail_calls = []

    @staticmethod
    def idempotency_key(*parts):
        return "execution-key"

    def get_execution(self, key):
        return {"execution_key": key, "mission_id": "MIS", "action_id": "ACT", "status": self.status}

    def confirm_execution_recovery_from_effect(self, key, provider_key):
        self.confirm_calls.append((key, provider_key))
        return {
            "execution_key": key,
            "mission_id": "MIS",
            "action_id": "ACT",
            "status": "COMPLETED",
            "result": '{"proved": true}',
            "error": None,
        }

    def resolve_execution_recovery(self, key, decision, *, reason=None):
        self.fail_calls.append((key, decision, reason))
        return {
            "execution_key": key,
            "mission_id": "MIS",
            "action_id": "ACT",
            "status": "FAILED",
            "result": None,
            "error": reason,
        }


class FakeCoordinator:
    def __init__(self, effect):
        self.effect = effect

    def peek(self, request):
        return self.effect


class FakeRuntime:
    @staticmethod
    def _action_fingerprint(action, mission_id):
        return "action-fp"


def _engine(status, effect_status=EffectStatus.COMPLETED.value):
    store = FakeStore(status)
    engine = object.__new__(DurableExecutionEngine)
    engine.store = store
    engine.runtime = FakeRuntime()
    engine.effect_coordinator = FakeCoordinator({"status": effect_status, "result": {"ignored": True}, "error": "remote failed"})
    engine._validate_execution_identity = lambda *args, **kwargs: None
    return engine, store


def test_completed_effect_finalizes_recovery_through_durable_proof():
    engine, store = _engine("RECOVERY_REQUIRED")
    action = SimpleNamespace(id="ACT")
    governed = SimpleNamespace(action=action)

    result = engine._execute_effect_authorized(action, "MIS", object(), provider_name="provider", operation="write", payload={"value": 1}, governed=governed)

    expected_key = EffectRequest(execution_key="execution-key", provider="provider", operation="write", payload={"value": 1}, action_fingerprint="action-fp").provider_idempotency_key
    assert result.status == "COMPLETED"
    assert result.result == {"proved": True}
    assert store.confirm_calls == [("execution-key", expected_key)]


def test_failed_effect_resolves_recovery_through_durable_failure():
    engine, store = _engine("RECOVERY_REQUIRED", EffectStatus.FAILED.value)
    action = SimpleNamespace(id="ACT")
    governed = SimpleNamespace(action=action)

    result = engine._execute_effect_authorized(action, "MIS", object(), provider_name="provider", operation="write", payload={"value": 1}, governed=governed)

    assert result.status == "FAILED"
    assert result.error == "remote failed"
    assert store.fail_calls == [("execution-key", "FAIL", "remote failed")]


def test_terminal_execution_is_not_rewritten_by_completed_effect():
    engine, store = _engine("COMPLETED")
    action = SimpleNamespace(id="ACT")
    governed = SimpleNamespace(action=action)

    result = engine._execute_effect_authorized(action, "MIS", object(), provider_name="provider", operation="write", payload={"value": 1}, governed=governed)

    assert result.status == "COMPLETED"
    assert store.confirm_calls == []
    assert store.fail_calls == []
