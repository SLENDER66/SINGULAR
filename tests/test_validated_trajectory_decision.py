import math
from dataclasses import FrozenInstanceError

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract, GovernorDecision
from singular.domain_learning import LearningDomain
from singular.global_control import GlobalDecisionReport
from singular.human_optimization import (
    DomainState,
    HumanOptimizationEngine,
    Intervention,
    OptimizationCandidate,
    OptimizationDisposition,
)
from singular.security import ActionPolicy, PolicyDecision
from singular.trajectory import TrajectoryAssessment, TrajectoryDecision
from singular.trajectory_optimization import TrajectoryPortfolio
from singular.validated_trajectory_decision import ValidatedTrajectoryDecision


def artifacts(*, global_decision: str = "PROCEED"):
    contract = DelegationContract("MIS-1", "Improve career", "Completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run a bounded career test", 4, 1, 9, contract_id=contract.mission_id)
    candidate = OptimizationCandidate("career", LearningDomain.CAREER, 1.2, 1.2, OptimizationDisposition.PROPOSE, (), False)
    human = HumanOptimizationEngine.optimize(
        (DomainState(LearningDomain.CAREER, 0.2, confidence=0.9),),
        (Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1),),
        capacity_budget=2,
    )
    portfolio = TrajectoryPortfolio((candidate,), 1.2, 1.0, 1.0, 0.0)
    assessment = TrajectoryAssessment(TrajectoryDecision.PROCEED, 0.8, 7.2, (), False)
    report = GlobalDecisionReport(
        objective="Improve career",
        action_id=action.id,
        decision=global_decision,
        blockers=(),
        warnings=(),
        capacity_recommendation=None,
        policy_tier="GREEN",
        policy_requires_human=False,
        governor_mode=Autonomy.PREPARE,
        red_team_findings=(),
        coherence=None,
        trajectory=assessment,
        human_optimization=human,
    )
    policy = PolicyDecision(ActionPolicy.evaluate(action).tier, True, True, False, ("safe",))
    governor = GovernorDecision(action.id, Autonomy.EXECUTE_REVERSIBLE, ("covered",))
    return action, human, portfolio, assessment, report, contract, policy, (), governor


def build(**overrides):
    action, human, portfolio, assessment, report, contract, policy, findings, governor = artifacts()
    values = {
        "decision_id": "DEC-1",
        "actions": (action,),
        "action_to_intervention": ((action.id, "career"),),
        "human_optimization": human,
        "trajectory_portfolio": portfolio,
        "trajectory_assessment": assessment,
        "global_report": report,
        "contract": contract,
        "policy": policy,
        "red_team_findings": findings,
        "governor": governor,
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
    action, human, portfolio, assessment, report, contract, policy, findings, governor = artifacts(global_decision=status)
    with pytest.raises(ValueError, match="PROCEED"):
        ValidatedTrajectoryDecision.create(
            decision_id="DEC-1", actions=(action,), action_to_intervention=((action.id, "career"),),
            human_optimization=human, trajectory_portfolio=portfolio, trajectory_assessment=assessment,
            global_report=report, contract=contract, policy=policy, red_team_findings=findings, governor=governor,
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("human_optimization", "human_optimization"),
        ("trajectory_portfolio", "trajectory_portfolio"),
        ("trajectory_assessment", "trajectory_assessment"),
        ("global_report", "global_report"),
        ("contract", "contract"),
        ("policy", "policy"),
        ("red_team_findings", "red_team_findings"),
        ("governor", "governor"),
    ],
)
def test_rejects_missing_required_context(field, message):
    with pytest.raises(ValueError, match=message):
        build(**{field: None})


def test_rejects_action_missing_from_portfolio():
    action, human, portfolio, assessment, report, contract, policy, findings, governor = artifacts()
    with pytest.raises(ValueError, match="portfolio"):
        ValidatedTrajectoryDecision.create(
            decision_id="DEC-1",
            actions=(action,),
            action_to_intervention=((action.id, "not-in-portfolio"),),
            human_optimization=human,
            trajectory_portfolio=portfolio,
            trajectory_assessment=assessment,
            global_report=report,
            contract=contract,
            policy=policy,
            red_team_findings=findings,
            governor=governor,
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_critical_numeric_context(value):
    _, _, portfolio, _, _, _, _, _, _ = artifacts()
    invalid = TrajectoryPortfolio(
        portfolio.candidates,
        value,
        portfolio.capacity_used,
        portfolio.capacity_remaining,
        portfolio.interaction_effect,
    )
    with pytest.raises(ValueError, match="finite"):
        build(trajectory_portfolio=invalid)


def test_detects_tampered_context_fingerprint():
    decision = build()
    object.__setattr__(decision, "global_report", artifacts(global_decision="BLOCK")[4])
    assert decision.verify() is False


def test_fingerprint_is_deterministic_for_identical_context():
    action, human, portfolio, assessment, report, contract, policy, findings, governor = artifacts()
    values = {
        "decision_id": "DEC-1",
        "actions": (action,),
        "action_to_intervention": ((action.id, "career"),),
        "human_optimization": human,
        "trajectory_portfolio": portfolio,
        "trajectory_assessment": assessment,
        "global_report": report,
        "contract": contract,
        "policy": policy,
        "red_team_findings": findings,
        "governor": governor,
    }
    first = ValidatedTrajectoryDecision.create(**values)
    second = ValidatedTrajectoryDecision.create(**values)
    assert first.context_fingerprint == second.context_fingerprint
