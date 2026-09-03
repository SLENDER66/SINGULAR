import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.domain_learning import LearningDomain
from singular.human_optimization import DomainState, Intervention
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision


def _inputs():
    contract = DelegationContract("MIS-PIPE", "Improve career", "Career action completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2, energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    return contract, action, state, intervention, profile, dimensions


def test_pipeline_constructs_decision_only_after_all_required_stages():
    contract, action, state, intervention, profile, dimensions = _inputs()
    decision = ValidatedTrajectoryPipeline.build(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        contract=contract,
        execution_target="tests.test_validated_pipeline:handler",
        decision_id="DEC-PIPE",
        capacity_budget=2,
    )
    assert decision.verify() is True
    assert decision.global_report.decision == "PROCEED"
    assert decision.trajectory_portfolio.candidates[0].intervention_id == intervention.id


def test_pipeline_fails_closed_when_trajectory_requires_review():
    contract, action, state, intervention, profile, dimensions = _inputs()
    dimensions["money"] = -0.2
    with pytest.raises(PermissionError, match="Global decision gate refused|Trajectory requires"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective,
            actions=(action,),
            action_to_intervention=((action.id, intervention.id),),
            domain_states=(state,),
            interventions=(intervention,),
            trajectory_profile=profile,
            trajectory_dimensions=dimensions,
            contract=contract,
            execution_target="tests.test_validated_pipeline:handler",
            decision_id="DEC-PIPE-BLOCK",
            capacity_budget=2,
        )


def test_pipeline_rejects_action_outside_selected_portfolio():
    contract, action, state, intervention, profile, dimensions = _inputs()
    with pytest.raises(PermissionError, match="outside the selected trajectory portfolio"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective,
            actions=(action,),
            action_to_intervention=((action.id, "wrong-intervention"),),
            domain_states=(state,),
            interventions=(intervention,),
            trajectory_profile=profile,
            trajectory_dimensions=dimensions,
            contract=contract,
            execution_target="tests.test_validated_pipeline:handler",
            decision_id="DEC-PIPE-MISMATCH",
            capacity_budget=2,
        )
