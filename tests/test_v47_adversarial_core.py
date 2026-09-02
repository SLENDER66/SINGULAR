from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine, ExecutionRecoveryRequired
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

    assert first == second
    assert calls == [1]


def test_execution_key_cannot_be_reused_across_missions(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    first = runtime.create_mission("first", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    second = runtime.create_mission("second", "done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    engine.execute(action, first.mission_id, lambda _: "ok")

    with pytest.raises((ValueError, PermissionError)):
        engine.execute(action, second.mission_id, lambda _: "must-not-run")


def test_stale_execution_cannot_reexecute_after_restart(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    mission = runtime.create_mission("stale", "recover", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    first = engine.execute(action, mission.mission_id, lambda _: "ok")
    assert first == "ok"

    # A fresh runtime sees the same durable terminal execution.
    restarted = DurableMissionRuntime(DurableStore(db))
    restarted_engine = DurableExecutionEngine(restarted)
    result = restarted_engine.execute(action, mission.mission_id, lambda _: "must-not-run")
    assert result == "ok"


def test_recovery_required_is_quarantined_and_requires_explicit_resolution(tmp_path: Path):
    db = tmp_path / "s.db"
    runtime = DurableMissionRuntime(DurableStore(db))
    mission = runtime.create_mission("ambiguous", "recover", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "run", 1, 1, 10)
    engine = DurableExecutionEngine(runtime)
    execution_key = engine.execution_key(action, mission.mission_id)
    runtime.store.begin_execution_and_start_mission(execution_key, mission.mission_id, action.id, lease_seconds=1)
    with runtime.store._connect() as conn:
        conn.execute("UPDATE executions SET lease_until='2000-01-01T00:00:00+00:00' WHERE execution_key=?", (execution_key,))

    with pytest.raises(ExecutionRecoveryRequired):
        engine.execute(action, mission.mission_id, lambda _: "must-not-run")

    assert runtime.store.get_execution(execution_key)["status"] == "RECOVERY_REQUIRED"


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


def test_illegal_state_transition_remains_impossible(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("state", "done", autonomy=Autonomy.PREPARE)

    with pytest.raises(ValueError, match="Transition de mission interdite"):
        store.set_mission_status(mission.mission_id, MissionStatus.COMPLETED)

    assert store.get_mission_status(mission.mission_id) == MissionStatus.CREATED
