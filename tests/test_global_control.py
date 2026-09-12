import sqlite3

from singular.autopilot import ActionRequest
from singular.coherence import GlobalCoherenceGuard
from singular.consistency import CrossDomainConsistencyChecker
from singular.global_control import GlobalDecisionGate
from singular.human_optimization import DomainState, HumanOptimizationEngine, Intervention
from singular.models import Risk
from singular.state import CapacitySnapshot
from singular.trajectory import TrajectoryProfile
from singular.values import CoreValue, ValueAssessment, ValuesEngine, Vision
from singular.world_model import EpistemicType, WorldFact, WorldModel
from singular.domain_learning import LearningDomain


def action(**overrides):
    data = {"name": "draft_plan", "description": "Préparer un plan", "impact": 8, "risk": 2, "reversibility": 8}
    data.update(overrides)
    return ActionRequest(**data)


def test_global_gate_proceeds_when_domains_are_coherent():
    world = WorldModel()
    world.upsert("objectives", WorldFact("o1", "stabiliser", EpistemicType.OBJECTIVE))
    values = [ValuesEngine.assess(CoreValue("freedom"), ValueAssessment.ALIGNED, "compatible")]
    report = GlobalDecisionGate().evaluate("stabiliser", action(), world_model=world, values=values, capacity=CapacitySnapshot(1, 0.1, 0.0, 1.0), effort=0.2)
    assert report.decision == "PROCEED"
    assert report.blockers == ()


def test_global_gate_propagates_global_trajectory_review():
    profile = TrajectoryProfile(Vision("Build durable freedom and ownership."))
    report = GlobalDecisionGate().evaluate("grow", action(), trajectory_profile=profile, trajectory_dimensions={"money": 0.9})
    assert report.decision == "REVIEW"
    assert report.trajectory is not None
    assert report.trajectory.human_review is True
    assert "TRAJECTORY:REVIEW" in report.warnings


def test_global_gate_blocks_value_violation():
    values = [ValuesEngine.assess(CoreValue("respect"), ValueAssessment.VIOLATED, "conflict")]
    report = GlobalDecisionGate().evaluate("objectif", action(), values=values)
    assert report.decision == "BLOCK"
    # The blocker names the violated value verbatim; upper-casing it would lose
    # which value it was when two differ only by case.
    assert "VALUES:HARD_CONSTRAINT_VIOLATED:respect" in report.blockers


def test_global_gate_reviews_unknown_values_and_low_confidence_state():
    values = [ValuesEngine.assess(CoreValue("freedom"), ValueAssessment.UNKNOWN)]
    report = GlobalDecisionGate().evaluate("objectif", action(), values=values, capacity=CapacitySnapshot(0.8, 0.2, 0.0, 0.4), effort=0.1)
    assert report.decision == "REVIEW"
    assert "VALUES:UNKNOWN_REQUIRES_HUMAN_REVIEW" in report.warnings
    assert "CAPACITY:CLARIFY_STATE" in report.warnings


def test_global_gate_blocks_high_risk_irreversible_risk():
    risk = Risk(id="r1", name="critical", probability=1.0, impact=9, reversibility=1)
    report = GlobalDecisionGate().evaluate("objectif", action(), risks=[risk])
    assert report.decision == "BLOCK"
    assert "RISK:HIGH_EXPOSURE:r1" in report.blockers


def test_global_gate_never_executes_sensitive_action():
    report = GlobalDecisionGate().evaluate("objectif", action(name="wire_money", sensitive=True))
    assert report.decision == "BLOCK"
    assert report.policy_tier == "BLACK"
    assert report.governor_mode.value == "ESCALATE"


def test_global_gate_carries_human_optimization_into_trajectory_control():
    human_report = HumanOptimizationEngine.optimize(
        (DomainState(LearningDomain.CAREER, 0.2, confidence=0.4, leverage=1.0),),
        (Intervention("career", LearningDomain.CAREER, 0.8, evidence=0.9, causal_confidence=0.9),),
    )
    report = GlobalDecisionGate().evaluate("career", action(), human_optimization=human_report)
    assert report.human_optimization is human_report
    assert report.decision == "REVIEW"
    assert "HUMAN_OPTIMIZATION:LOW_STATE_CONFIDENCE" in report.warnings


def test_global_gate_fails_closed_on_durable_coherence_violation(tmp_path):
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE mission_states (mission_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE executions (execution_key TEXT PRIMARY KEY, mission_id TEXT NOT NULL, action_id TEXT, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE external_effects (provider_idempotency_key TEXT PRIMARY KEY, execution_key TEXT NOT NULL, status TEXT NOT NULL)")
        conn.execute("INSERT INTO mission_states VALUES ('M1', 'COMPLETED')")
        conn.execute("INSERT INTO executions VALUES ('E1', 'M1', 'A1', 'RUNNING')")
        conn.commit()

    gate = GlobalDecisionGate(coherence_guard=GlobalCoherenceGuard(CrossDomainConsistencyChecker(db)))
    report = gate.evaluate("objectif", action(), mission_id="M1")
    assert report.decision == "BLOCK"
    assert "COHERENCE:MISSION_COMPLETED_WITH_NONTERMINAL_EXECUTION" in report.blockers
