import pytest

from singular.collective_intelligence import (
    CollectiveIntelligence,
    KnowledgeKind,
    SharedSignal,
)


def test_collective_view_preserves_consensus_and_dissent() -> None:
    signals = (
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "opportunity", "test first", 0.9),
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "opportunity", "test first", 0.8),
        SharedSignal("RED_TEAM", KnowledgeKind.CHALLENGE, "opportunity", "do not test", 0.7),
    )
    view = CollectiveIntelligence.deliberate("opportunity", signals)
    assert view.consensus == "test first"
    assert view.dissent == ("do not test",)
    assert view.contributors == ("INTELLIGENCE", "RED_TEAM", "STRATEGY")
    assert view.unresolved is False


def test_no_majority_is_unresolved() -> None:
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 0.5),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "B", 0.5),
    )
    view = CollectiveIntelligence.deliberate("x", signals)
    assert view.consensus is None
    assert view.unresolved is True
    # Nothing was agreed, so both claims are dissent. Listing only the
    # lower-weighted one implied the other had been accepted.
    assert view.dissent == ("A", "B")


def test_subject_without_signals_is_fail_closed() -> None:
    """No evidence yields an unresolved deliberation, not a raised error.

    This test only accepted a ValueError, so the fail-closed return value it
    describes counted as a failure. deliberate() does raise for an empty subject
    string -- a different condition, asserted separately below.
    """
    view = CollectiveIntelligence.deliberate("missing", ())
    assert view.consensus is None
    assert view.unresolved is True
    assert view.signals == ()


def test_empty_subject_string_is_rejected() -> None:
    with pytest.raises(ValueError, match="subject is required"):
        CollectiveIntelligence.deliberate("", ())


def test_one_contributor_each_way_is_not_a_consensus() -> None:
    """A weighted majority is not a majority of minds.

    EVIDENCE outweighs ANALYSIS, so a single evidence signal used to outvote a
    single analysis signal from a different contributor and be reported as
    consensus -- removing the unresolved flag that makes the global gate ask for
    a human.
    """
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 0.9),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "B", 0.1),
    )
    view = CollectiveIntelligence.deliberate("x", signals)
    assert view.consensus is None
    assert view.unresolved is True


def test_a_real_contributor_majority_still_reaches_consensus() -> None:
    """The guard must discriminate, not make consensus unreachable."""
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 0.6),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "A", 0.6),
        SharedSignal("FINANCE", KnowledgeKind.ANALYSIS, "x", "B", 0.9),
    )
    view = CollectiveIntelligence.deliberate("x", signals)
    assert view.consensus == "A"
    assert view.unresolved is False


def test_collective_boundary_preserves_hierarchy() -> None:
    boundaries = CollectiveIntelligence.authority_boundary()
    assert "shared_knowledge_is_not_shared_authority" in boundaries
    assert "consensus_is_not_authorization" in boundaries
    assert "human_final_authority_is_preserved" in boundaries


def test_repeated_claims_from_one_agent_do_not_create_fake_majority() -> None:
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 1.0),
        SharedSignal("STRATEGY", KnowledgeKind.RECOMMENDATION, "x", "A", 1.0),
        SharedSignal("RED_TEAM", KnowledgeKind.CHALLENGE, "x", "B", 0.9),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "B", 0.9),
    )
    view = CollectiveIntelligence.deliberate("x", signals)
    assert view.consensus is None
    assert view.unresolved is True


def test_calibration_reduces_confidence_inflation() -> None:
    """Calibration moves weight, and must not manufacture agreement.

    This asserted that down-weighting one of two disagreeing contributors turned
    the other into the consensus. One contributor each way is a disagreement
    whatever the weights: calibration is there to stop an over-confident
    contributor dominating, not to resolve a split that two minds actually have.
    """
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 1.0),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "B", 0.8),
    )
    uncalibrated = CollectiveIntelligence.deliberate("x", signals)
    calibrated = CollectiveIntelligence.deliberate("x", signals, calibration={"STRATEGY": 0.2})

    assert calibrated.consensus is None and calibrated.unresolved is True
    assert uncalibrated.consensus is None and uncalibrated.unresolved is True
    # The disputed claim's share of the weight moves away from the down-weighted
    # contributor even though neither side wins.
    assert calibrated.collective_confidence > uncalibrated.collective_confidence


def test_calibration_can_change_which_claim_leads_a_real_majority() -> None:
    """Calibration still bites where a majority of contributors exists."""
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 1.0),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "B", 0.8),
        SharedSignal("FINANCE", KnowledgeKind.ANALYSIS, "x", "B", 0.8),
    )
    view = CollectiveIntelligence.deliberate("x", signals, calibration={"STRATEGY": 0.2})
    assert view.consensus == "B"
    assert view.unresolved is False


def test_critical_red_team_challenge_blocks_consensus() -> None:
    signals = (
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "execute", 1.0),
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "execute", 0.9),
        SharedSignal("RED_TEAM", KnowledgeKind.CHALLENGE, "x", "critical failure", 0.95, critical=True),
    )
    view = CollectiveIntelligence.deliberate("x", signals)
    assert view.consensus is None
    assert view.unresolved is True
    assert view.blocking_challenges == ("critical failure",)


def test_unknown_calibration_is_fail_closed() -> None:
    signal = SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 0.8)
    try:
        CollectiveIntelligence.deliberate("x", (signal,), calibration={"STRATEGY": float("nan")})
    except ValueError:
        assert True
    else:
        raise AssertionError("invalid calibration must fail closed")
