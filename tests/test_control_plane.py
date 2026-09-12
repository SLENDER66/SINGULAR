from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.global_control import SingularControlPlane
from singular.human_optimization import DomainState, Intervention
from singular.domain_learning import LearningDomain
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.values import Vision
from singular.durable import DurableStore
from singular.execution_capability import register_execution_capability

from tests.test_validated_pipeline import authorized_handler


def _plane(tmp_path: Path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    return runtime, SingularControlPlane(runtime)


def _kwargs(decision_id="DEC-CONTROL", execution_target=None):
    contract = DelegationContract("MIS-CONTROL", "Improve career", "Career action completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2, energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    if execution_target is None:
        execution_target = register_execution_capability(authorized_handler, "cap_test_control_authorized_handler")
    return dict(
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


def test_control_plane_exposes_verified_execution_as_canonical_safe_path(tmp_path):
    runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs("DEC-CONTROL-VERIFY"))
    action_id = control_decision.decision.global_report.action_id

    result = plane.execute_verified(
        control_decision,
        action_id,
        authorized_handler,
        lambda action, execution: execution.result == {"action_id": action.id, "executed": True},
    )

    assert result.status == "COMPLETED"
    assert any(
        event.category == "verification" and event.outcome == "VERIFIED"
        for event in runtime.audit.events()
    )


def test_control_plane_builds_attests_and_executes_through_one_surface(tmp_path):
    _runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs())
    result = plane.execute(control_decision, control_decision.decision.global_report.action_id, authorized_handler)
    assert result.status == "COMPLETED"


def test_control_plane_revoke_prevents_future_execution(tmp_path):
    _runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs("DEC-CONTROL-REVOKE"))
    plane.revoke(control_decision)
    with pytest.raises(PermissionError):
        plane.execute(control_decision, control_decision.decision.global_report.action_id, authorized_handler)


def test_control_plane_outcome_closes_learning_loop(tmp_path):
    _runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs("DEC-CONTROL-LEARN"))
    action_id = control_decision.decision.global_report.action_id
    result = plane.execute(control_decision, action_id, authorized_handler)
    assert result.status == "COMPLETED"

