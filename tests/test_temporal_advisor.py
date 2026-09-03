import pytest

from singular.history_world_model import (
    EpistemicLevel,
    FutureDisposition,
    FutureScenario,
    HistoricalEvidence,
    HistoricalMode,
    build_temporal_context,
)
from singular.temporal_advisor import TemporalAdvisor


def _context():
    evidence = HistoricalEvidence(
        "E1", "Observed event", "archive", EpistemicLevel.ESTABLISHED_FACT, 0.9,
        HistoricalMode.RESILIENCE, mechanisms=("institutional-friction",),
    )
    scenarios = (
        FutureScenario("PREP", 3.0, "A prepared future", 0.8, evidence_ids=("E1",), assumptions=("mechanism persists",), disposition=FutureDisposition.PREPARE),
        FutureScenario("WATCH", 5.0, "A monitored future", 0.5, evidence_ids=("E1",), assumptions=("mechanism persists",), disposition=FutureDisposition.WATCH),
    )
    return build_temporal_context(as_of="2026-09-03", evidence=(evidence,), scenarios=scenarios)


def test_temporal_advisor_orders_signals_deterministically():
    advisory = TemporalAdvisor().assess(_context())
    assert [signal.scenario_id for signal in advisory.signals] == ["PREP", "WATCH"]
    assert advisory.preparation_scenarios == ("PREP",)
    assert advisory.watch_scenarios == ("WATCH",)


def test_temporal_advisor_never_authorizes():
    advisory = TemporalAdvisor().assess(_context())
    assert advisory.blocked_from_authorization is True
    assert TemporalAdvisor.can_authorize(advisory) is False


def test_empty_advisory_is_maximally_uncertain():
    context = build_temporal_context(as_of="2026-09-03", evidence=(), scenarios=())
    advisory = TemporalAdvisor().assess(context)
    assert advisory.signals == ()
    assert advisory.uncertainty == 1.0


def test_advisory_rejects_unknown_preparation_reference():
    with pytest.raises(ValueError, match="unknown scenario"):
        from singular.temporal_advisor import TemporalAdvisory
        TemporalAdvisory((), ("UNKNOWN",), ())
