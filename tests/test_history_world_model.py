import math

import pytest

from singular.history_world_model import (
    EpistemicLevel,
    FutureDisposition,
    FutureReasoner,
    FutureScenario,
    HistoricalEvidence,
    HistoricalMode,
    HistoricalReasoner,
    TemporalContext,
    WorldStateSnapshot,
    build_temporal_context,
)


def evidence(eid="E1", *, level=EpistemicLevel.ESTABLISHED_FACT, reliability=0.9, mechanisms=("institutional-friction",)):
    return HistoricalEvidence(
        id=eid,
        statement="Observed historical event",
        source="archive",
        level=level,
        reliability=reliability,
        mode=HistoricalMode.CONSTRUCTION,
        mechanisms=mechanisms,
    )


def scenario(sid="S1", *, horizon=5.0, probability=0.7, evidence_ids=("E1",)):
    return FutureScenario(
        id=sid,
        horizon_years=horizon,
        statement="A plausible future condition",
        probability=probability,
        evidence_ids=evidence_ids,
        assumptions=("Current causal mechanism persists",),
        disposition=FutureDisposition.PREPARE,
    )


def test_only_fact_like_evidence_enters_canonical_world():
    contested = evidence("EC", level=EpistemicLevel.CONTESTED, reliability=0.95)
    fact = evidence("EF")
    context = build_temporal_context(as_of="2026-09-03", evidence=(contested, fact), scenarios=(scenario(),))
    assert {item.id for item in context.canonical_world.canonical_facts} == {"EF"}
    assert context.canonical_world.verify()


def test_future_scenario_is_never_authorization():
    assert FutureReasoner.authorize_from_future(scenario()) is False


def test_low_reliability_does_not_become_high_confidence():
    low = evidence(reliability=0.1)
    assessment = FutureReasoner.assess(scenario(probability=0.9), (low,))
    assert assessment.confidence < 0.2
    assert assessment.uncertainty > 0.8


def test_contested_evidence_reduces_future_confidence():
    fact = evidence("EF", reliability=0.9)
    contested = evidence("EC", level=EpistemicLevel.CONTESTED, reliability=0.9)
    near_fact = FutureReasoner.assess(scenario(evidence_ids=("EF",)), (fact, contested))
    challenged = FutureReasoner.assess(scenario(evidence_ids=("EF", "EC")), (fact, contested))
    assert challenged.confidence < near_fact.confidence
    assert "CONTESTED_EVIDENCE_PRESENT" in challenged.reasons


def test_long_horizon_reduces_confidence_and_surfaces_uncertainty():
    near = FutureReasoner.assess(scenario(horizon=2.0), (evidence(),))
    far = FutureReasoner.assess(scenario(horizon=50.0), (evidence(),))
    assert far.confidence < near.confidence
    assert "LONG_HORIZON" in far.reasons


def test_constructive_and_destructive_evidence_can_coexist():
    items = (
        evidence("BUILD", mechanisms=("specialization",)),
        HistoricalEvidence("DESTROY", "Observed breakdown", "archive", EpistemicLevel.PROBABLE_FACT, 0.8,
                           HistoricalMode.DESTRUCTION, mechanisms=("specialization",)),
    )
    patterns = HistoricalReasoner.derive_patterns(items)
    assert len(patterns) == 1
    assert set(patterns[0].evidence_ids) == {"BUILD", "DESTROY"}


def test_contested_evidence_remains_visible_as_counterevidence():
    items = (evidence("EF"), evidence("EC", level=EpistemicLevel.CONTESTED, reliability=0.7))
    pattern = HistoricalReasoner.derive_patterns(items)[0]
    assert pattern.counterevidence == ("EC",)


def test_temporal_context_rejects_pattern_set_mismatch():
    context = build_temporal_context(as_of="2026-09-03", evidence=(evidence(),), scenarios=(scenario(),))
    with pytest.raises(ValueError, match="patterns"):
        TemporalContext((), context.active_scenarios, context.canonical_world)


def test_snapshot_rejects_injected_contested_canonical_fact():
    snapshot = WorldStateSnapshot.build("2026-09-03", (evidence(),), (), ())
    contested = evidence("EC", level=EpistemicLevel.CONTESTED)
    object.__setattr__(snapshot, "canonical_facts", (contested,))
    assert not snapshot.verify()


def test_snapshot_fingerprint_detects_tampering():
    snapshot = WorldStateSnapshot.build("2026-09-03", (evidence(),), (), (scenario(),))
    assert snapshot.verify()
    object.__setattr__(snapshot, "as_of", "forged")
    assert not snapshot.verify()


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_future_inputs_reject_non_finite_values(value):
    with pytest.raises(ValueError):
        FutureScenario("S", value, "x", 0.5, assumptions=("a",))


@pytest.mark.parametrize("mechanisms", [(), ("",), ("valid", "")])
def test_historical_evidence_rejects_empty_mechanisms(mechanisms):
    with pytest.raises(ValueError, match="mechanism"):
        evidence(mechanisms=mechanisms)
