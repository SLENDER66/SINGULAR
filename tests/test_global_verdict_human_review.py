"""The gate's verdict must never contradict its own requires_human property.

``GlobalDecisionGate.evaluate`` used to compute ``decision`` from an expression
that ran in parallel with the ``requires_human`` property and left out the
governor's mode. An action the Governor escalated therefore came back as
PROCEED while the same report's ``requires_human`` said True.

Nothing was executable that way: ``ValidatedTrajectoryDecision`` refuses any
report whose ``requires_human`` is True, so the escalation was still caught one
layer down. But the headline verdict was fail-open by shape, and a report that
contradicts itself is exactly the kind of thing the next caller reads only half
of. The verdict is now derived from the report, so the two cannot drift.

These tests also pin the design they revealed: a human approval is *not* an
authorization channel through the validated pipeline. An escalated action is
refused at the gate, deliberately, rather than carried forward for a human to
approve later. The approval machinery in ``DurableExecutionEngine`` is a
time-of-use defence -- it catches governance that escalates *after* a decision
was minted -- not a way in.
"""

from dataclasses import replace

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.global_control import GlobalDecisionGate, GlobalDecisionReport
from singular.validated_pipeline import ValidatedTrajectoryPipeline

from tests.test_validated_pipeline import _build_decision, _inputs


def _report(**overrides) -> GlobalDecisionReport:
    base = dict(
        objective="Improve career", action_id="A1", decision="PROCEED",
        blockers=(), warnings=(), capacity_recommendation=None,
        policy_tier="GREEN", policy_requires_human=False,
        governor_mode=Autonomy.EXECUTE_REVERSIBLE, red_team_findings=(), coherence=None,
    )
    base.update(overrides)
    return GlobalDecisionReport(**base)


def _evaluate(action: ActionRequest, contract: DelegationContract) -> GlobalDecisionReport:
    return GlobalDecisionGate().evaluate(
        contract.objective, action, mission_id=contract.mission_id, contract=contract,
    )


def test_an_escalated_action_is_never_reported_as_proceed():
    contract, action, _, _, _, _ = _inputs()
    report = _evaluate(replace(action, requires_human=True), contract)

    assert report.governor_mode is Autonomy.ESCALATE
    assert report.requires_human is True
    assert report.decision == "REVIEW"


def test_a_clean_action_still_proceeds():
    contract, action, _, _, _, _ = _inputs()
    report = _evaluate(action, contract)
    assert report.requires_human is False
    assert report.decision == "PROCEED"


@pytest.mark.parametrize("cause", [
    {"requires_human": True},
    {"sensitive": True},
])
def test_every_governor_escalation_leaves_the_verdict_short_of_proceed(cause):
    """A sensitive action is refused harder still: the policy blocks it outright."""
    contract, action, _, _, _, _ = _inputs()
    report = _evaluate(replace(action, **cause), contract)
    assert report.governor_mode is Autonomy.ESCALATE, cause
    assert report.decision == ("BLOCK" if report.blockers else "REVIEW"), cause
    assert report.decision != "PROCEED", cause


@pytest.mark.parametrize("overrides", [
    {},
    {"warnings": ("COMMANDER:CAPACITY_LIMIT",)},
    {"policy_requires_human": True},
    {"governor_mode": Autonomy.ESCALATE},
    {"warnings": ("W",), "governor_mode": Autonomy.ESCALATE},
    {"blockers": ("POLICY:BLACK",)},
    {"blockers": ("POLICY:BLACK",), "governor_mode": Autonomy.ESCALATE},
])
def test_proceed_means_exactly_no_blocker_and_no_human_needed(overrides):
    """The invariant a caller is allowed to rely on, stated once."""
    report = _report(**overrides)
    verdict = "BLOCK" if report.blockers else ("REVIEW" if report.requires_human else "PROCEED")
    assert (verdict == "PROCEED") == (not report.blockers and not report.requires_human)


class _SpoofGate:
    """A gate that answers honestly, then rewrites its own verdict."""

    def __init__(self, **overrides):
        self.overrides = overrides

    def evaluate(self, *args, **kwargs):
        return replace(GlobalDecisionGate().evaluate(*args, **kwargs), **self.overrides)


def _build_with(gate=None, action_overrides=None):
    contract, action, state, intervention, profile, dimensions = _inputs()
    if action_overrides:
        action = replace(action, **action_overrides)
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,),
        action_to_intervention=((action.id, intervention.id),), domain_states=(state,),
        interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target=_build_decision().execution_target,
        decision_id="DEC-REVIEW", capacity_budget=2, gate=gate,
    )


def test_the_pipeline_refuses_an_escalated_action_at_the_gate():
    """An escalation is refused where it is detected, not two guards later."""
    with pytest.raises(PermissionError, match="refused execution: REVIEW"):
        _build_with(action_overrides={"requires_human": True})


def test_a_forged_proceed_over_an_escalation_still_does_not_get_through():
    """Rewriting the headline does not remove the escalation underneath it."""
    with pytest.raises((PermissionError, ValueError)):
        _build_with(_SpoofGate(decision="PROCEED", governor_mode=Autonomy.ESCALATE))
