from singular.models import WorldModel
from singular.v3_operating_system import *


def test_decision_engine_prefers_high_leverage_reversible_action():
    world = WorldModel()
    eng = DecisionEngine()
    candidates = [
        CandidateAction("build_skill", 8, 5, 9, 2, 2, 9, 8),
        CandidateAction("buy_asset", 9, 5, 4, 3, 7, 4, 5),
    ]
    a = eng.assess(candidates, world)
    assert a.action.name == "build_skill"
    assert a.needs_human is False


def test_world_model_does_not_hide_signal_uncertainty():
    system = SingularV3()
    system.observe([Signal(SignalType.CHANGE, "test", "Une nouvelle opportunité apparaît", 0.6)])
    assert len(system.world.evidence) == 1
    assert system.world.evidence[0].certainty == "HYPOTHESIS"
    assert system.world.evidence[0].confidence == 0.6


def test_high_risk_escalates():
    system = SingularV3()
    cycle = system.cycle([], [CandidateAction("wire_money", 9, 9, 8, 1, 9, 1, 8)])
    assert cycle.assessment.needs_human is True
    assert cycle.assessment.recommendation == "ESCALATE"


def test_learning_loop():
    system = SingularV3()
    rec = LearningRecord("H", "P", "A", 0.2, "lesson", 0.8)
    learning = system.learning.record(system.world, rec)
    assert learning.lesson == "lesson"
    assert len(system.world.learnings) == 1


def test_architect_proposes_but_does_not_apply():
    system = SingularV3()
    change = system.architect.propose("latency", ["trace"], "cache", "faster", "low", "benchmark", ["p95 < 200ms"], "remove cache")
    assert change.modification == "cache"
    assert not hasattr(system, "auto_apply_change")


def test_snapshot_reports_pending_human_load():
    system = SingularV3()
    system.cycle([], [CandidateAction("sign_contract", 9, 8, 7, 1, 8, 1)])
    # decision itself is recorded; no approval is created until the action is submitted.
    snap = system.snapshot()
    assert snap.human_intervention_required is True
    assert snap.next_action == "sign_contract"
