from pathlib import Path
from threading import Event, Thread

import pytest

from singular.audit import AuditTrail
from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine, ExecutionInProgress, ExecutionRecoveryRequired
from singular.effects import ExternalEffectCoordinator, ProviderResult
from singular.mission_runtime import DurableMissionRuntime


class CountingProvider:
    def __init__(self):
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        return ProviderResult("COMPLETED", {"calls": self.execute_calls})

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return ProviderResult("COMPLETED", {"reconciled": True})


def test_replay_completed_execution_is_durable_and_does_not_reexecute(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("replay", "completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    calls = []

    first = engine.execute(action, mission.mission_id, lambda _: calls.append(1) or "ok")
    second = engine.execute(action, mission.mission_id, lambda _: calls.append(1) or "must-not-run")

    assert first.status == "COMPLETED"
    assert second == first
    assert first.result == "ok"
    assert calls == [1]


def test_execution_identity_is_durable_and_tamper_evident(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("identity", "durable", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    first = engine.execute(action, mission.mission_id, lambda _: "ok")
    assert first.status == "COMPLETED"

    execution_key = store.idempotency_key("execute", mission.mission_id, action.id)
    identity_key = store.idempotency_key("execution_identity", execution_key)
    with store._connect() as conn:
        conn.execute("UPDATE idempotency SET fingerprint='tampered' WHERE key=?", (identity_key,))

    with pytest.raises((ValueError, PermissionError), match="Identité|autorité|contenu"):
        engine.execute(action, mission.mission_id, lambda _: pytest.fail("tampered replay must not execute"))


def test_missing_execution_identity_fails_closed_on_replay(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("identity-missing", "durable", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    first = engine.execute(action, mission.mission_id, lambda _: "ok")
    assert first.status == "COMPLETED"

    execution_key = store.idempotency_key("execute", mission.mission_id, action.id)
    identity_key = store.idempotency_key("execution_identity", execution_key)
    with store._connect() as conn:
        conn.execute("DELETE FROM idempotency WHERE key=?", (identity_key,))

    with pytest.raises(PermissionError, match="Identité d'exécution absente"):
        engine.execute(action, mission.mission_id, lambda _: pytest.fail("missing identity must not replay"))


def test_execution_key_cannot_be_reused_across_missions(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    first = runtime.create_mission("first", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    second = runtime.create_mission("second", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    key = store.idempotency_key("manual-collision")
    first_result = store.begin_execution(key, first.mission_id, action.id)
    assert first_result["claimed"] is True

    with pytest.raises(ValueError, match="Identité d'exécution réutilisée"):
        store.begin_execution(key, second.mission_id, action.id)


def test_execution_key_cannot_change_action_under_same_mission(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("same mission", "identity", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    first = ActionRequest("safe_action", "run", 1, 1, 10)
    second = ActionRequest("other_action", "run", 1, 1, 10)
    key = store.idempotency_key("manual-collision")
    store.begin_execution(key, mission.mission_id, first.id)

    with pytest.raises(ValueError, match="Identité d'exécution réutilisée"):
        store.begin_execution(key, mission.mission_id, second.id)


def test_concurrent_workers_have_one_execution_owner(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("concurrent", "single owner", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine_a = DurableExecutionEngine(runtime)
    engine_b = DurableExecutionEngine(DurableMissionRuntime(store))
    started = Event()
    release = Event()
    calls = []
    first_result = []

    def handler(_):
        calls.append("handler")
        started.set()
        assert release.wait(timeout=5)
        return "ok"

    def run_first():
        first_result.append(engine_a.execute(action, mission.mission_id, handler))

    worker = Thread(target=run_first)
    worker.start()
    assert started.wait(timeout=5)

    with pytest.raises(ExecutionInProgress):
        engine_b.execute(action, mission.mission_id, lambda _: pytest.fail("second worker must not execute"))

    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert [result.status for result in first_result] == ["COMPLETED"]
    assert calls == ["handler"]
    assert store.get_execution(store_key(store, mission.mission_id, action.id))["status"] == "COMPLETED"
    assert store.get_mission_status(mission.mission_id) == MissionStatus.COMPLETED


def test_stale_execution_cannot_reexecute_after_restart(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    mission = runtime.create_mission("stale", "recover", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    runtime.store.set_mission_status(mission.mission_id, MissionStatus.PLANNED)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    execution_key = store_key(runtime.store, mission.mission_id, action.id)
    runtime.store.begin_execution_and_start_mission(execution_key, mission.mission_id, action.id, lease_seconds=1)
    with runtime.store._connect() as conn:
        conn.execute("UPDATE executions SET lease_until='2000-01-01T00:00:00+00:00' WHERE execution_key=?", (execution_key,))

    restarted = DurableMissionRuntime(DurableStore(db))
    restarted_engine = DurableExecutionEngine(restarted)
    with pytest.raises(ExecutionRecoveryRequired):
        restarted_engine.execute(action, mission.mission_id, lambda _: pytest.fail("stale execution must not reexecute"))

    assert restarted.store.get_execution(execution_key)["status"] == "RECOVERY_REQUIRED"


def test_recovery_required_is_quarantined_and_requires_explicit_resolution(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    mission = runtime.create_mission("ambiguous", "recover", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    runtime.store.set_mission_status(mission.mission_id, MissionStatus.PLANNED)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    execution_key = store_key(runtime.store, mission.mission_id, action.id)
    runtime.store.begin_execution_and_start_mission(execution_key, mission.mission_id, action.id, lease_seconds=1)
    with runtime.store._connect() as conn:
        conn.execute("UPDATE executions SET lease_until='2000-01-01T00:00:00+00:00' WHERE execution_key=?", (execution_key,))

    with pytest.raises(ExecutionRecoveryRequired):
        engine.execute(action, mission.mission_id, lambda _: pytest.fail("recovery-required execution must not run"))

    assert runtime.store.get_execution(execution_key)["status"] == "RECOVERY_REQUIRED"


def store_key(store: DurableStore, mission_id: str, action_id: str) -> str:
    return store.idempotency_key("execute", mission_id, action_id)


def test_provider_ambiguity_never_retries_provider_execute(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("provider", "reconcile", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "send", 1, 1, 10)
    provider = CountingProvider()
    coordinator = ExternalEffectCoordinator(store)
    engine = DurableExecutionEngine(runtime, effect_coordinator=coordinator)

    class TimeoutProvider(CountingProvider):
        def execute(self, request, idempotency_key):
            self.execute_calls += 1
            raise TimeoutError("lost")

    uncertain = TimeoutProvider()
    first = engine.execute_effect(action, mission.mission_id, uncertain, provider_name="fake", operation="send", payload={"x": 1})
    assert first.status == "RECOVERY_REQUIRED"
    assert uncertain.execute_calls == 1

    result = engine.reconcile_effect(action, mission.mission_id, provider, provider_name="fake", operation="send", payload={"x": 1})
    assert result.status == "COMPLETED"
    assert uncertain.execute_calls == 1
    assert provider.execute_calls == 0
    assert provider.reconcile_calls == 1


def test_persisted_audit_event_verifies_and_detects_payload_tampering(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    event = AuditTrail().record("execution", "TEST", "COMPLETED", {"mission_id": "M1", "value": 42})
    store.record_audit(event)

    persisted = dict(store.audit_events()[0])
    assert AuditTrail.verify_persisted_event(persisted) is True

    tampered = dict(persisted)
    tampered["payload"] = dict(persisted["payload"])
    tampered["payload"]["value"] = 43
    assert AuditTrail.verify_persisted_event(tampered) is False


def test_persisted_audit_event_without_fingerprint_fails_closed():
    event = {
        "id": "AUD-test",
        "event_type": "execution",
        "actor": "TEST",
        "outcome": "COMPLETED",
        "payload": {"mission_id": "M1"},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    assert AuditTrail.verify_persisted_event(event) is False


def test_illegal_state_transition_remains_impossible(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("state", "done", autonomy=Autonomy.PREPARE)

    with pytest.raises(ValueError, match="Transition de mission interdite"):
        store.set_mission_status(mission.mission_id, MissionStatus.COMPLETED)

    assert store.get_mission_status(mission.mission_id) == MissionStatus.CREATED
