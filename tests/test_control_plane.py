import pytest

from singular.control_plane import ControlPlaneDecision, SingularControlPlane
from singular.durable import DurableStore
from singular.learning import Forecast, ForecastKind
from singular.mission_runtime import DurableMissionRuntime
from tests.test_validated_pipeline import AUTHORIZED_HANDLER_CAPABILITY, _inputs, authorized_handler


def _plane(tmp_path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "control.db"))
    return runtime, SingularControlPlane(runtime, issuer="control-test")


def _kwargs(decision_id="DEC-CONTROL"):
    contract, action, state, intervention, profile, dimensions = _inputs()
    return dict(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        contract=contract,
        execution_target=AUTHORIZED_HANDLER_CAPABILITY,
        decision_id=decision_id,
        capacity_budget=2,
    )


def test_control_plane_builds_attests_and_executes_through_one_surface(tmp_path):
    runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs())
    result = plane.execute(control_decision, control_decision.decision.global_report.action_id, authorized_handler)
    assert isinstance(control_decision, ControlPlaneDecision)
    assert result.status == "COMPLETED"


def test_control_plane_revoke_prevents_future_execution(tmp_path):
    runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs("DEC-CONTROL-REVOKE"))
    plane.revoke(control_decision)
    with pytest.raises(PermissionError, match="attestée"):
        plane.execute(control_decision, control_decision.decision.global_report.action_id, authorized_handler)


def test_control_plane_outcome_closes_learning_loop(tmp_path):
    runtime, plane = _plane(tmp_path)
    control_decision = plane.construct_and_attest(**_kwargs("DEC-CONTROL-LEARN"))
    forecast = Forecast("F-CONTROL", ForecastKind.BINARY, probability=0.8, confidence=0.9)
    result = plane.observe_outcome(
        control_decision,
        forecast=forecast,
        actual=True,
        execution_key="EXEC-CONTROL",
        execution_status="COMPLETED",
        observed_at="2026-09-03T19:30:00+00:00",
    )
    assert result.outcome.context_fingerprint == control_decision.decision.context_fingerprint
    assert result.review.status == "PENDING"
