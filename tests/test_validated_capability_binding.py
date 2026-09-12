import pytest
from dataclasses import replace

from singular.autopilot import ActionRequest
from singular.execution_capability import register_execution_capability
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from tests.test_validated_pipeline import _inputs


def test_pipeline_binds_source_action_to_execution_capability():
    contract, action, state, intervention, profile, dimensions = _inputs()

    capability = register_execution_capability(lambda _action: None, "cap_binding_test")
    decision = ValidatedTrajectoryPipeline.build(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        contract=contract,
        execution_target=capability,
        decision_id="DEC-CAP-BIND",
        capacity_budget=2,
    )

    assert decision.authorized_actions[0].execution_capability == capability
    # The governance capability field stays untouched: a cap_ token is not a
    # CapabilityRegistry name and ActionPolicy would refuse it as tier BLACK.
    assert decision.authorized_actions[0].capability is None
    assert decision.verify()


def test_pipeline_rejects_conflicting_source_action_capability():
    contract, action, state, intervention, profile, dimensions = _inputs()
    first = register_execution_capability(lambda _action: None, "cap_binding_conflict_a")
    second = register_execution_capability(lambda _action: None, "cap_binding_conflict_b")
    conflicting = replace(action, execution_capability=first)

    with pytest.raises(PermissionError, match="action capability"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective,
            actions=(conflicting,),
            action_to_intervention=((action.id, intervention.id),),
            domain_states=(state,),
            interventions=(intervention,),
            trajectory_profile=profile,
            trajectory_dimensions=dimensions,
            contract=contract,
            execution_target=second,
            decision_id="DEC-CAP-CONFLICT",
            capacity_budget=2,
        )
