from singular.models import Opportunity
from singular.opportunity_adapter import OpportunityAdapter
from singular.world_model import OpportunityClass, WorldOpportunity


def test_world_opportunity_converts_to_decision_model() -> None:
    world = WorldOpportunity(
        name="Prototype",
        potential=0.9,
        probability=0.7,
        cost=2.0,
        time=1.0,
        risk=3.0,
        reversibility=0.8,
        synergies=("career", "business"),
        classification=OpportunityClass.OUTLIER,
    )

    result = OpportunityAdapter.to_decision_model("opp-1", world)

    assert isinstance(result, Opportunity)
    assert result.id == "opp-1"
    assert result.impact == 9.0
    assert result.probability == 0.7
    assert result.reversibility == 8.0
    assert result.cost == 2.0
    assert result.risk == 3.0
    assert result.optionality == 6.0


def test_world_model_conversion_is_deterministic() -> None:
    first = WorldOpportunity("A", 0.5, 0.5, 1, 1, 2, 0.5)
    second = WorldOpportunity("B", 0.8, 0.5, 1, 1, 1, 0.5)
    opportunities = {"b": second, "a": first}

    result = OpportunityAdapter.world_model_opportunities(opportunities)

    assert [item.id for item in result] == ["a", "b"]
    assert [item.name for item in result] == ["A", "B"]
