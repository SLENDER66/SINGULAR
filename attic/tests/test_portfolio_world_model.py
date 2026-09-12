from singular.portfolio import PortfolioEngine
from singular.world_model import WorldModel, WorldOpportunity


def test_portfolio_engine_consumes_canonical_world_model() -> None:
    world = WorldModel()
    world.add_opportunity(WorldOpportunity("A", 0.9, 0.8, 1, 1, 1, 0.9))
    world.add_opportunity(WorldOpportunity("B", 0.4, 0.6, 4, 1, 4, 0.5))

    result = PortfolioEngine.optimize_world(world, budget=5, risk_budget=5, max_positions=2)

    assert result.selections
    assert result.total_cost <= 5
    assert result.total_risk <= 5
    assert set(result.rejected_ids).isdisjoint({item.opportunity_id for item in result.selections})
