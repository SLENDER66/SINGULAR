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
    assert view.dissent == ("B",)


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
