import math
from dataclasses import FrozenInstanceError, replace
from time import time

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract, GovernorDecision
from singular.domain_learning import LearningDomain
from singular.global_control import GlobalDecisionGate
from singular.human_optimization import DomainState, HumanOptimizationEngine, Intervention
from singular.security import ActionPolicy
from singular.trajectory import TrajectoryAssessment, TrajectoryDecision, TrajectoryEngine, TrajectoryProfile
from singular.trajectory_optimization import TrajectoryPortfolio
from singular.validated_trajectory_decision import ValidatedTrajectoryDecision, payload_fingerprint
from singular.values import Vision


VALID_FROM = time()
VALID_TO = VALID_FROM + 3600.0
HANDLER_CAPABILITY = "cap_test_authorized_handler"
PROVIDER_CAPABILITY = "cap_test_provider"


def artifacts(*, global_decision: str = "PROCEED"):
    contract = DelegationContract("MIS-1", "Improve career", "Completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    # The action must carry the execution capability the decision authorizes:
    # a decision whose action is bound to no executable authorizes nothing in
    # particular, which is what ValidatedTrajectoryDecision._validate refuses.
    # A fixed id: ActionRequest mints a random one per instance, so two builds
    # of the "identical context" could never produce the same fingerprint.
    action = ActionRequest("career_test", "Run a bounded career test", 4, 1, 9,
                           contract_id=contract.mission_id, id="ACT-VTD-FIXED",
                           execution_capability=HANDLER_CAPABILITY)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    human = HumanOptimizationEngine.optimize((state,), (intervention,), capacity_budget=2)
    candidate = human.candidates[0]
    portfolio = TrajectoryPortfolio((candidate,), candidate.score, 1.0, 1.0, 0.0)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2,
                               energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    assessment = TrajectoryEngine.assess(profile, dimensions=dimensions, portfolio=portfolio)
    governor = GovernorDecision(action.id, Autonomy.EXECUTE_REVERSIBLE, ("Action couverte par le contrat d'autonomie.",))
    policy = ActionPolicy.evaluate(action)
    report = GlobalDecisionGate().evaluate(
        contract.objective,
        action,
        mission_id=contract.mission_id,
        contract=contract,
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        trajectory_portfolio=portfolio,
        human_optimization=human,
    )
    if report.decision != global_decision:
        report = replace(report, decision=global_decision)
    return action, state, intervention, human, portfolio, profile, dimensions, assessment, report, contract, policy, (), governor


def build(**overrides):
    action, state, intervention, human, portfolio, profile, dimensions, assessment, report, contract, policy, findings, governor = artifacts()
    values = {
        "decision_id": "DEC-1", "issued_at": VALID_FROM, "expires_at": VALID_TO,
        "actions": (action,), "action_to_intervention": ((action.id, "career"),),
        "domain_states": (state,), "interventions": (intervention,), "human_interactions": (), "trajectory_interactions": (),
        "trajectory_profile": profile, "trajectory_dimensions": dimensions, "value_results": (), "capacity": None, "effort": None,
        "risks": (), "shared_signals": (), "calibration": {}, "portfolio_capacity_budget": 2, "portfolio_max_candidates": 5,
        "human_optimization": human, "trajectory_portfolio": portfolio, "trajectory_assessment": assessment,
        "global_report": report, "contract": contract, "policy": policy, "red_team_findings": findings,
        "governor": governor, "execution_target": HANDLER_CAPABILITY,
    }
    values.update(overrides)
    return ValidatedTrajectoryDecision.create(**values)


def recreate(decision, **overrides):
    values = {
        "decision_id": decision.decision_id, "issued_at": decision.issued_at, "expires_at": decision.expires_at,
        "actions": tuple(action.to_action() for action in decision.authorized_actions),
        "action_to_intervention": decision.action_to_intervention, "domain_states": decision.domain_states,
        "interventions": decision.interventions, "human_interactions": decision.human_interactions,
        "trajectory_interactions": decision.trajectory_interactions, "trajectory_profile": decision.trajectory_profile,
        "trajectory_dimensions": dict(decision.trajectory_dimensions), "value_results": decision.value_results,
        "capacity": decision.capacity, "effort": decision.effort, "risks": decision.risks,
        "shared_signals": decision.shared_signals, "calibration": dict(decision.calibration),
        "portfolio_capacity_budget": decision.portfolio_capacity_budget, "portfolio_max_candidates": decision.portfolio_max_candidates,
        "human_optimization": decision.human_optimization, "trajectory_portfolio": decision.trajectory_portfolio,
        "trajectory_assessment": decision.trajectory_assessment, "global_report": decision.global_report,
        "contract": decision.contract, "policy": decision.policy, "red_team_findings": decision.red_team_findings,
        "governor": decision.governor, "execution_target": decision.execution_target,
        "execution_kind": decision.execution_kind, "provider_name": decision.provider_name,
        "provider_target": decision.provider_target, "operation": decision.operation,
        "payload_fingerprint": decision.payload_fingerprint,
    }
    values.update(overrides)
    return ValidatedTrajectoryDecision.create(**values)


def test_creates_valid_immutable_tamper_evident_decision():
    decision = build()
    assert decision.verify() is True
    assert decision.authorized_actions[0].id == decision.global_report.action_id
    with pytest.raises(FrozenInstanceError):
        decision.decision_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("status", ["REVIEW", "BLOCK"])
def test_rejects_non_proceed_global_report(status):
    action, state, intervention, human, portfolio, profile, dimensions, assessment, report, contract, policy, findings, governor = artifacts(global_decision=status)
    with pytest.raises(ValueError, match="PROCEED"):
        ValidatedTrajectoryDecision.create(
            decision_id="DEC-1", issued_at=VALID_FROM, expires_at=VALID_TO,
            actions=(action,), action_to_intervention=((action.id, "career"),),
            domain_states=(state,), interventions=(intervention,), human_interactions=(), trajectory_interactions=(),
            trajectory_profile=profile, trajectory_dimensions=dimensions, value_results=(), capacity=None, effort=None,
            risks=(), shared_signals=(), calibration={}, portfolio_capacity_budget=2, portfolio_max_candidates=5,
            human_optimization=human, trajectory_portfolio=portfolio, trajectory_assessment=assessment,
            global_report=report, contract=contract, policy=policy, red_team_findings=findings, governor=governor,
            execution_target=HANDLER_CAPABILITY,
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [("human_optimization", "human_optimization"), ("trajectory_portfolio", "trajectory_portfolio"),
     ("trajectory_assessment", "trajectory_assessment"), ("global_report", "global_report"), ("contract", "contract"),
     ("policy", "policy"), ("red_team_findings", "red_team_findings"), ("governor", "governor")],
)
def test_rejects_missing_required_context(field, message):
    with pytest.raises(ValueError, match=message):
        build(**{field: None})


def test_rejects_action_missing_from_portfolio():
    action, state, intervention, human, portfolio, profile, dimensions, assessment, report, contract, policy, findings, governor = artifacts()
    with pytest.raises(ValueError, match="share the validated intervention"):
        ValidatedTrajectoryDecision.create(
            decision_id="DEC-1", issued_at=VALID_FROM, expires_at=VALID_TO,
            actions=(action,), action_to_intervention=((action.id, "not-in-portfolio"),),
            domain_states=(state,), interventions=(intervention,), human_interactions=(), trajectory_interactions=(),
            trajectory_profile=profile, trajectory_dimensions=dimensions, value_results=(), capacity=None, effort=None,
            risks=(), shared_signals=(), calibration={}, portfolio_capacity_budget=2, portfolio_max_candidates=5,
            human_optimization=human, trajectory_portfolio=portfolio, trajectory_assessment=assessment,
            global_report=report, contract=contract, policy=policy, red_team_findings=findings, governor=governor,
            execution_target=HANDLER_CAPABILITY,
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_critical_numeric_context(value):
    """Construction refuses a non-finite value; the message names the fingerprint.

    create() fingerprints the payload before __post_init__ runs _validate, so the
    canonical-JSON guard (allow_nan=False) is what rejects here. This test used to
    demand the portfolio message and so asserted an ordering that has never held.
    """
    _, _, _, _, portfolio, _, _, _, _, _, _, _, _ = artifacts()
    invalid = TrajectoryPortfolio(portfolio.candidates, value, portfolio.capacity_used, portfolio.capacity_remaining, portfolio.interaction_effect)
    with pytest.raises(ValueError, match="must be finite"):
        build(trajectory_portfolio=invalid)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_portfolio_injected_after_construction_fails_verification(value):
    """The other path: a value smuggled past construction must not verify.

    Here _validate runs before the payload is fingerprinted, so the targeted
    portfolio guard is the one that fires. Both guards are live, on different
    paths -- asserting only one of them would leave the other unproven.
    """
    decision = build()
    portfolio = decision.trajectory_portfolio
    invalid = TrajectoryPortfolio(portfolio.candidates, value, portfolio.capacity_used, portfolio.capacity_remaining, portfolio.interaction_effect)
    object.__setattr__(decision, "trajectory_portfolio", invalid)
    with pytest.raises(ValueError, match="trajectory portfolio"):
        decision._validate(now=decision.issued_at)
    assert decision.verify() is False


def test_detects_tampered_context_fingerprint():
    decision = build()
    object.__setattr__(decision, "global_report", replace(decision.global_report, decision="BLOCK"))
    assert decision.verify() is False


def test_fingerprint_is_deterministic_for_identical_context():
    first = build()
    second = build()
    assert first.context_fingerprint == second.context_fingerprint


def test_temporal_validity_is_part_of_the_fingerprint():
    decision = build()
    object.__setattr__(decision, "expires_at", decision.expires_at + 1)
    assert decision.verify() is False
    assert decision.verify(now=VALID_TO) is False


def test_global_report_cannot_be_forged_without_matching_gate_inputs():
    """Forge a field no targeted guard inspects, so only reconstruction can catch it.

    These tests used to forge `warnings`, which GlobalDecisionReport.requires_human
    derives from: the decision was refused by the human-review guard before the gate
    was ever re-evaluated, so they proved that guard rather than reconstruction.
    capacity_recommendation feeds no other check.
    """
    decision = build()
    forged = replace(decision.global_report, capacity_recommendation="FORGED_RECOMMENDATION")
    assert forged.requires_human == decision.global_report.requires_human
    assert forged.can_prepare == decision.global_report.can_prepare
    with pytest.raises(ValueError, match="global decision report does not match its validated gate inputs"):
        recreate(decision, global_report=forged)


def test_global_report_tampering_is_rejected_even_when_fingerprint_is_rebuilt():
    """recreate() recomputes context_fingerprint, so integrity cannot be the reason."""
    decision = build()
    forged = replace(decision.global_report, blockers=("FORGED_BLOCKER",))
    with pytest.raises(ValueError):
        recreate(decision, global_report=forged)


def test_forged_warning_is_refused_even_though_another_guard_catches_it_first():
    """Whichever guard fires, a forged report never becomes a validated decision."""
    decision = build()
    forged = replace(decision.global_report, warnings=("FORGED_WARNING",))
    assert forged.requires_human is True
    with pytest.raises(ValueError):
        recreate(decision, global_report=forged)
