"""`capability` and `execution_capability` answer two different questions.

`capability` is a name from CapabilityRegistry: it decides what an action is
*allowed* to be, and ActionPolicy refuses any name it does not know as tier
BLACK. `execution_capability` is an opaque `cap_...` token from
ExecutionCapabilityRegistry: it identifies *which code* may run, and carries no
permission of its own.

They used to share one field. The validated pipeline stamped the execution token
into `capability`, ActionPolicy could not resolve it, every action became tier
BLACK, the global gate answered BLOCK, and no ValidatedTrajectoryDecision could
ever be built. The boundary was not fail-closed pending migration; the authorized
path did not exist. These tests keep the two apart in both directions.
"""
from dataclasses import replace

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.capabilities import CapabilityRegistry
from singular.execution_capability import register_execution_capability
from singular.security import ActionPolicy
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.validated_trajectory_decision import ValidatedActionRequest
from tests.test_validated_pipeline import (
    AUTHORIZED_HANDLER_CAPABILITY,
    _build_decision,
    _inputs,
)


def _action() -> ActionRequest:
    return ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id="MIS-PIPE")


def test_execution_token_never_reaches_the_policy():
    """The decisive regression: an opaque token must not be read as a policy name."""
    bare = _action()
    bound = replace(bare, execution_capability="cap_policy_probe")
    assert ActionPolicy.evaluate(bound) == ActionPolicy.evaluate(bare)
    assert ActionPolicy.evaluate(bound).can_execute is True


def test_execution_token_in_the_governance_field_is_still_refused():
    """The old confusion must fail loudly if it is ever reintroduced."""
    smuggled = replace(_action(), capability="cap_test_authorized_handler")
    decision = ActionPolicy.evaluate(smuggled)
    assert decision.tier.value == "BLACK"
    assert decision.can_execute is False
    assert CapabilityRegistry.resolve("cap_test_authorized_handler") is None


def test_governance_name_is_rejected_as_an_execution_token():
    with pytest.raises(ValueError, match="opaque cap_ token"):
        replace(_action(), execution_capability="send_email")


def test_blank_execution_token_is_rejected():
    with pytest.raises(ValueError, match="execution_capability"):
        replace(_action(), execution_capability="   ")


def test_pipeline_leaves_the_governance_capability_alone():
    decision = _build_decision()
    action = decision.authorized_actions[0]
    assert action.execution_capability == decision.execution_target
    assert action.capability is None


def test_decision_rejects_an_action_with_no_execution_capability():
    """Building a decision outside the pipeline must not skip the binding."""
    decision = _build_decision()
    unbound = replace(decision.authorized_actions[0], execution_capability=None)
    with pytest.raises(ValueError, match="validated execution capability"):
        replace(decision, authorized_actions=(unbound,))


def test_decision_rejects_an_action_bound_to_another_execution_capability():
    decision = _build_decision()
    other = register_execution_capability(lambda _action: None, "cap_separation_other")
    swapped = replace(decision.authorized_actions[0], execution_capability=other)
    with pytest.raises(ValueError, match="validated execution capability"):
        replace(decision, authorized_actions=(swapped,))


def test_execution_capability_is_inside_the_decision_fingerprint():
    """A binding outside context_fingerprint would be tamperable metadata."""
    decision = _build_decision()
    tampered = replace(decision.authorized_actions[0], execution_capability="cap_tampered_target")
    object.__setattr__(decision, "authorized_actions", (tampered,))
    assert decision.verify() is False


def test_validated_action_round_trip_preserves_both_fields():
    action = replace(_action(), capability="read_email", execution_capability=AUTHORIZED_HANDLER_CAPABILITY)
    restored = ValidatedActionRequest.from_action(action).to_action()
    assert restored.capability == "read_email"
    assert restored.execution_capability == AUTHORIZED_HANDLER_CAPABILITY


def test_pipeline_still_refuses_an_unknown_governance_capability():
    """Separating the fields must not weaken governance on the field that keeps it."""
    contract, action, state, intervention, profile, dimensions = _inputs()
    ungoverned = replace(action, capability="not_a_registered_capability")
    with pytest.raises(PermissionError, match="Global decision gate refused"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(ungoverned,),
            action_to_intervention=((ungoverned.id, intervention.id),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target=AUTHORIZED_HANDLER_CAPABILITY,
            decision_id="DEC-UNKNOWN-CAP", capacity_budget=2,
        )


def test_pipeline_still_refuses_a_capability_mismatched_with_the_action_name():
    contract, action, state, intervention, profile, dimensions = _inputs()
    mismatched = replace(action, capability="read_email")
    assert ActionPolicy.evaluate(mismatched).tier.value == "BLACK"
    with pytest.raises(PermissionError, match="Global decision gate refused"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(mismatched,),
            action_to_intervention=((mismatched.id, intervention.id),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target=AUTHORIZED_HANDLER_CAPABILITY,
            decision_id="DEC-MISMATCH-CAP", capacity_budget=2,
        )


def test_contract_autonomy_is_unchanged_by_the_split():
    contract = DelegationContract("MIS-SEP", "Improve career", "Done", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    assert contract.autonomy is Autonomy.EXECUTE_REVERSIBLE
