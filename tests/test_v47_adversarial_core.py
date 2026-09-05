from pathlib import Path
from threading import Event, Thread

import pytest

from singular.audit import AuditTrail
from singular.autopilot import ActionRequest, Autonomy
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.durable import DurableStore, MissionStatus
from singular.effects import ExternalEffectCoordinator, ProviderResult
from singular.execution import DurableExecutionEngine, ExecutionInProgress, ExecutionRecoveryRequired
from singular.execution_capability import register_execution_capability
from singular.mission_runtime import DurableMissionRuntime
from singular.recovery import RecoveryDecision, RecoveryManager
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.domain_learning import LearningDomain
from singular.human_optimization import DomainState, Intervention
from singular.trajectory import TrajectoryProfile
from singular.values import Vision


#: Every invocation of an authorized handler, so a replay that must not execute
#: can be proved by the counter rather than by a canary the boundary would
#: reject anyway. These tests used to pass an inline lambda as the "must not
#: run" handler; once decisions bind an exact executable, such a lambda is
#: refused for not being the authorized capability, which proves nothing about
#: replay, idempotency or lease ownership.
CALLS: list[str] = []


def authorized_handler(action):
    CALLS.append(action.id)
    return {"action_id": action.id, "executed": True}


AUTHORIZED_HANDLER_CAPABILITY = register_execution_capability(authorized_handler, "cap_v47_authorized_handler")

BLOCK_UNTIL = Event()
STARTED = Event()


def blocking_handler(action):
    """The authorized executable for the concurrency test; holds the lease open."""
    CALLS.append(action.id)
    STARTED.set()
    assert BLOCK_UNTIL.wait(timeout=5)
    return "ok"


BLOCKING_HANDLER_CAPABILITY = register_execution_capability(blocking_handler, "cap_v47_blocking_handler")


@pytest.fixture(autouse=True)
def _reset_call_log():
    CALLS.clear()
    STARTED.clear()
    BLOCK_UNTIL.clear()
    yield
    BLOCK_UNTIL.set()


def _inputs(*, decision_id: str = "DEC-V47", execution_target: str = AUTHORIZED_HANDLER_CAPABILITY):
    from singular.autopilot import DelegationContract

    contract = DelegationContract("MIS-V47", "Adversarial execution", "completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("safe_action", "Execute bounded action", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build resilient capability"), money=1, time=1, capability=2, energy=1,
                               freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    decision = ValidatedTrajectoryPipeline.build(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        contract=contract,
        execution_target=execution_target,
        decision_id=decision_id,
        capacity_budget=2,
    )
    return contract, action, decision


def _runtime_and_engine(tmp_path: Path, decision):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    runtime.store.save_mission(decision.contract)
    engine = DurableExecutionEngine(runtime)
    ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
    return runtime, engine


def test_replay_completed_execution_is_durable_and_does_not_reexecute(tmp_path: Path):
    _, action, decision = _inputs()
    runtime, engine = _runtime_and_engine(tmp_path, decision)

    first = engine.execute_validated(decision, authorized_handler)
    second = engine.execute_validated(decision, authorized_handler)

    assert first.status == "COMPLETED"
    assert second == first
    assert first.result == {"action_id": action.id, "executed": True}
    assert CALLS == [action.id]


def test_execution_identity_is_durable_and_tamper_evident(tmp_path: Path):
    _, action, decision = _inputs()
    runtime, engine = _runtime_and_engine(tmp_path, decision)
    engine.execute_validated(decision, authorized_handler)
    execution_key = runtime.store.idempotency_key("execute", decision.contract.mission_id, action.id)
    identity_key = runtime.store.idempotency_key("execution_identity", execution_key)

    with runtime.store._connect() as conn:
        conn.execute("UPDATE idempotency SET fingerprint='tampered' WHERE key=?", (identity_key,))

    executed_before = len(CALLS)
    with pytest.raises(PermissionError, match="Identité|autorité|contenu"):
        engine.execute_validated(decision, authorized_handler)
    assert len(CALLS) == executed_before, "a tampered identity must not re-run the handler"


def test_missing_execution_identity_fails_closed_on_replay(tmp_path: Path):
    _, action, decision = _inputs()
    runtime, engine = _runtime_and_engine(tmp_path, decision)
    engine.execute_validated(decision, authorized_handler)
    execution_key = runtime.store.idempotency_key("execute", decision.contract.mission_id, action.id)
    identity_key = runtime.store.idempotency_key("execution_identity", execution_key)

    with runtime.store._connect() as conn:
        conn.execute("DELETE FROM idempotency WHERE key=?", (identity_key,))

    executed_before = len(CALLS)
    with pytest.raises(PermissionError, match="Identité d'exécution absente"):
        engine.execute_validated(decision, authorized_handler)
    assert len(CALLS) == executed_before, "a missing identity must not re-run the handler"


def test_concurrent_workers_have_one_execution_owner(tmp_path: Path):
    _, action, decision = _inputs(decision_id="DEC-CONCURRENT", execution_target=BLOCKING_HANDLER_CAPABILITY)
    runtime, engine_a = _runtime_and_engine(tmp_path, decision)
    engine_b = DurableExecutionEngine(DurableMissionRuntime(DurableStore(tmp_path / "s.db")))
    first_result = []

    def run_first():
        first_result.append(engine_a.execute_validated(decision, blocking_handler))

    worker = Thread(target=run_first)
    worker.start()
    assert STARTED.wait(timeout=5)

    # Same decision, same authorized executable, second worker: only the lease
    # may decide, so this must be refused while the first holds it.
    with pytest.raises(ExecutionInProgress):
        engine_b.execute_validated(decision, blocking_handler)

    BLOCK_UNTIL.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert [result.status for result in first_result] == ["COMPLETED"]
    assert CALLS == [action.id]


def test_stale_execution_cannot_reexecute_after_restart(tmp_path: Path):
    _, action, decision = _inputs(decision_id="DEC-STALE")
    runtime, engine = _runtime_and_engine(tmp_path, decision)
    runtime.store.set_mission_status(decision.contract.mission_id, MissionStatus.PLANNED)
    execution_key = runtime.store.idempotency_key("execute", decision.contract.mission_id, action.id)
    runtime.store.begin_execution_and_start_mission(execution_key, decision.contract.mission_id, action.id, lease_seconds=1)
    with runtime.store._connect() as conn:
        conn.execute("UPDATE executions SET lease_until='2000-01-01T00:00:00+00:00' WHERE execution_key=?", (execution_key,))

    restarted = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    restarted_engine = DurableExecutionEngine(restarted)
    executed_before = len(CALLS)
    with pytest.raises(ExecutionRecoveryRequired):
        restarted_engine.execute_validated(decision, authorized_handler)
    assert len(CALLS) == executed_before, "a stale lease must not re-run the handler after restart"
    assert runtime.store.get_execution(execution_key)["status"] == "RECOVERY_REQUIRED"


def test_recovery_required_is_quarantined_and_cannot_be_confirmed_by_fiat(tmp_path: Path):
    """An operator may abandon an ambiguous execution, never declare it succeeded.

    This test used to assert that RecoveryDecision.CONFIRM produced COMPLETED.
    RecoveryManager now refuses CONFIRM unconditionally: a successful outcome has
    to come from provider reconciliation, which has external evidence, rather
    than from an operator asserting it through a generic API. Asserting the old
    behaviour would be asserting the absence of that control.
    """
    _, action, decision = _inputs(decision_id="DEC-RECOVERY")
    runtime, engine = _runtime_and_engine(tmp_path, decision)
    runtime.store.set_mission_status(decision.contract.mission_id, MissionStatus.PLANNED)
    execution_key = runtime.store.idempotency_key("execute", decision.contract.mission_id, action.id)
    runtime.store.begin_execution_and_start_mission(execution_key, decision.contract.mission_id, action.id, lease_seconds=1)
    runtime.store.mark_execution_recovery_required(execution_key)

    with pytest.raises(ExecutionRecoveryRequired):
        engine._handle_existing_execution(execution_key, runtime.store.get_execution(execution_key))

    manager = RecoveryManager(runtime.store)
    with pytest.raises(ValueError, match="preuve externe"):
        manager.resolve(execution_key, RecoveryDecision.CONFIRM, result={"already": True})
    assert runtime.store.get_execution(execution_key)["status"] == "RECOVERY_REQUIRED"

    resolved = manager.resolve(execution_key, RecoveryDecision.FAIL, reason="outcome unknown")
    assert resolved.execution_status == "FAILED"
    assert CALLS == [], "resolving a quarantined execution must never run the handler"


def test_raw_execution_api_is_closed(tmp_path: Path):
    contract, action, _ = _inputs(decision_id="DEC-RAW")
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    runtime.store.save_mission(contract)
    engine = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.execute(action, contract.mission_id, authorized_handler)


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


def test_illegal_state_transition_remains_impossible(tmp_path: Path):
    store = DurableStore(tmp_path / "s.db")
    runtime = DurableMissionRuntime(store)
    mission = runtime.create_mission("state", "done", autonomy=Autonomy.PREPARE)
    with pytest.raises(ValueError, match="Transition de mission interdite"):
        store.set_mission_status(mission.mission_id, MissionStatus.COMPLETED)
    assert store.get_mission_status(mission.mission_id) == MissionStatus.CREATED


def test_external_effect_ambiguity_never_reexecutes_provider(tmp_path: Path):
    class Provider:
        def __init__(self):
            self.execute_calls = 0
            self.reconcile_calls = 0

        def execute(self, request, idempotency_key):
            self.execute_calls += 1
            raise TimeoutError("lost")

        def reconcile(self, request, idempotency_key):
            self.reconcile_calls += 1
            return ProviderResult("COMPLETED", {"confirmed": True})

    provider = Provider()
    capability = register_execution_capability(provider, "cap_v47_provider")
    from singular.autopilot import DelegationContract
    contract = DelegationContract("MIS-EFFECT", "External effect", "completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("external_action", "apply", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Bounded external operation"), money=1, time=1, capability=2, energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    decision = ValidatedTrajectoryPipeline.build(
        objective=contract.objective,
        actions=(action,), action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract, execution_target=capability,
        execution_kind="external_effect", provider_name="fake-provider",
        provider_target="tests.test_v47_adversarial_core:Provider", operation="send",
        execution_payload={"x": 1}, decision_id="DEC-EFFECT", capacity_budget=2,
    )
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "effects.db"))
    runtime.store.save_mission(contract)
    coordinator = ExternalEffectCoordinator(runtime.store)
    engine = DurableExecutionEngine(runtime, effect_coordinator=coordinator)
    ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
    first = engine.execute_effect_validated(decision, provider, provider_name="fake-provider", operation="send", payload={"x": 1})
    assert first.status == "RECOVERY_REQUIRED"
    assert provider.execute_calls == 1
    provider_result = engine.reconcile_effect_validated(decision, provider, provider_name="fake-provider", operation="send", payload={"x": 1})
    assert provider_result.status == "COMPLETED"
    assert provider.reconcile_calls == 1
