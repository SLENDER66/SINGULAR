from singular.collective_intelligence import CollectiveIntelligence, KnowledgeKind, SharedSignal


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
        SharedSignal("RED_TEAM", KnowledgeKind.CHALLENGE, "x", "B", 0.5),
    )
    view = CollectiveIntelligence.deliberate("x", signals)
    assert view.consensus is None
    assert view.unresolved is True
    assert view.dissent == ()


def test_empty_subject_is_fail_closed() -> None:
    try:
        CollectiveIntelligence.deliberate("missing", ())
    except ValueError:
        assert True
    else:
        raise AssertionError("missing evidence must remain unresolved")


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
    signals = (
        SharedSignal("STRATEGY", KnowledgeKind.ANALYSIS, "x", "A", 1.0),
        SharedSignal("INTELLIGENCE", KnowledgeKind.EVIDENCE, "x", "B", 0.8),
    )
    view = CollectiveIntelligence.deliberate("x", signals, calibration={"STRATEGY": 0.2})
    assert view.consensus == "B"
    assert view.collective_confidence > 0.8


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
