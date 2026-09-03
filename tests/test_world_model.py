import pytest

from singular.world_model import (
    EpistemicType,
    OpportunityClass,
    TemporalState,
    WorldFact,
    WorldModel,
    WorldOpportunity,
)


def test_fact_requires_source_and_valid_confidence():
    with pytest.raises(ValueError, match="requires a source"):
        WorldFact("income", 1000, EpistemicType.FACT)
    with pytest.raises(ValueError, match="between 0 and 1"):
        WorldFact("x", 1, EpistemicType.ESTIMATE, confidence=1.1)


def test_world_model_keeps_epistemic_types_and_unknowns_explicit():
    model = WorldModel()
    model.upsert("facts", WorldFact("job", "unemployed", EpistemicType.FACT, source="user", temporal=TemporalState.CURRENT))
    model.upsert("resources", WorldFact("english", "learning", EpistemicType.HYPOTHESIS, confidence=0.6))
    model.upsert("risks", WorldFact("debt", "unknown_total", EpistemicType.UNKNOWN, confidence=0.2))

    assert model.get("facts", "job").epistemic == EpistemicType.FACT
    assert [item.key for item in model.unknowns()] == ["debt"]


def test_outlier_opportunities_are_ranked_by_leverage():
    model = WorldModel()
    model.add_opportunity(WorldOpportunity("A", 0.9, 0.8, 0.1, 0.1, 0.1, 0.9, classification=OpportunityClass.OUTLIER))
    model.add_opportunity(WorldOpportunity("B", 0.8, 0.7, 0.5, 0.5, 0.5, 0.5, classification=OpportunityClass.OUTLIER))
    model.add_opportunity(WorldOpportunity("C", 1.0, 1.0, 0.0, 0.0, 0.0, 1.0))

    ranked = model.outlier_opportunities()
    assert [item.name for item in ranked] == ["A", "B"]
    assert model.get("opportunities", "C").classification == OpportunityClass.NORMAL


def test_snapshot_exposes_unknown_and_outlier_counts():
    model = WorldModel()
    model.upsert("facts", WorldFact("x", None, EpistemicType.UNKNOWN))
    model.add_opportunity(WorldOpportunity("moonshot", 1, 0.5, 0.1, 0.1, 0.1, 1, classification=OpportunityClass.OUTLIER))

    snapshot = model.snapshot()
    assert snapshot["unknowns"] == 1
    assert snapshot["outlier_opportunities"] == 1
