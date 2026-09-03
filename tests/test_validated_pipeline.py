import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision
from singular.validated_trajectory_decision import payload_fingerprint


def _inputs():
    contract = DelegationContract("MIS-PIPE", "Improve career", "Career action completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2, energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    return contract, action, state, intervention, profile, dimensions


def _build_decision():
    contract, action, state, intervention, profile, dimensions = _inputs()
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target="tests.test_validated_pipeline:authorized_handler",
        decision_id="DEC-PIPE", capacity_budget=2,
    )


def authorized_handler(action):
    return {"action_id": action.id, "executed": True}


def test_pipeline_constructs_decision_only_after_all_required_stages():
    decision = _build_decision()
    assert decision.verify() is True
    assert decision.global_report.decision == "PROCEED"
    assert decision.trajectory_portfolio.candidates[0].intervention_id == "career"


def test_pipeline_fails_closed_when_trajectory_requires_review():
    contract, action, state, intervention, profile, dimensions = _inputs()
    dimensions["money"] = -0.2
    with pytest.raises(PermissionError, match="Global decision gate refused|Trajectory requires"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target="tests.test_validated_pipeline:authorized_handler",
            decision_id="DEC-PIPE-BLOCK", capacity_budget=2,
        )


def test_pipeline_rejects_action_outside_selected_portfolio():
    contract, action, state, intervention, profile, dimensions = _inputs()
    with pytest.raises(PermissionError, match="outside the selected trajectory portfolio"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(action,), action_to_intervention=((action.id, "wrong-intervention"),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target="tests.test_validated_pipeline:authorized_handler",
            decision_id="DEC-PIPE-MISMATCH", capacity_budget=2,
        )


def test_executor_rejects_handler_substitution_before_handler_call(tmp_path):
    decision = _build_decision()
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    executor = DurableExecutionEngine(runtime)
    calls = []

    with pytest.raises(PermissionError, match="execution target"):
        executor.execute_validated(decision, lambda action: calls.append("wrong"))

    assert calls == []


def test_executor_accepts_only_the_bound_handler(tmp_path):
    decision = _build_decision()
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    executor = DurableExecutionEngine(runtime)

    result = executor.execute_validated(decision, authorized_handler)

    assert result.status == "COMPLETED"
    assert result.result["executed"] is True


class AuthorizedProvider:
    def execute(self, request, idempotency_key):
        raise AssertionError("provider should not be called by substitution tests")

    def reconcile(self, request, idempotency_key):
        raise AssertionError("provider should not be called by substitution tests")


class OtherProvider(AuthorizedProvider):
    pass


def _build_effect_decision():
    contract, action, state, intervention, profile, dimensions = _inputs()
    payload = {"amount": 42, "target": "bounded"}
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target="tests.test_validated_pipeline:AuthorizedProvider", execution_kind="external_effect",
        provider_name="bounded-provider", provider_target="tests.test_validated_pipeline:AuthorizedProvider",
        operation="apply", execution_payload=payload, decision_id="DEC-EFFECT", capacity_budget=2,
    ), payload


def test_executor_rejects_provider_substitution_before_runtime_access(tmp_path):
    decision, _ = _build_effect_decision()
    executor = object.__new__(DurableExecutionEngine)
    with pytest.raises(PermissionError, match="Provider implementation"):
        executor.execute_effect_validated(decision, OtherProvider(), provider_name="bounded-provider", operation="apply", payload={"amount": 42, "target": "bounded"})


def test_executor_rejects_operation_substitution_before_runtime_access(tmp_path):
    decision, payload = _build_effect_decision()
    executor = object.__new__(DurableExecutionEngine)
    with pytest.raises(PermissionError, match="Provider or operation"):
        executor.execute_effect_validated(decision, AuthorizedProvider(), provider_name="bounded-provider", operation="delete", payload=payload)


def test_executor_rejects_payload_substitution_before_runtime_access(tmp_path):
    decision, _ = _build_effect_decision()
    executor = object.__new__(DurableExecutionEngine)
    with pytest.raises(PermissionError, match="payload"):
        executor.execute_effect_validated(decision, AuthorizedProvider(), provider_name="bounded-provider", operation="apply", payload={"amount": 43, "target": "bounded"})


def test_payload_fingerprint_is_stable_for_equivalent_mapping_order():
    assert payload_fingerprint({"b": 2, "a": 1}) == payload_fingerprint({"a": 1, "b": 2})
