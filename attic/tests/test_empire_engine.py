from singular.empire_engine import EmpireAsset, EmpireEngine, EmpireStage


def test_empty_portfolio_is_foundation() -> None:
    result = EmpireEngine.assess([])
    assert result.stage is EmpireStage.FOUNDATION
    assert result.priorities == ("BUILD_FIRST_PRODUCTIVE_ASSET",)


def test_owned_productive_assets_create_compounding_stage() -> None:
    result = EmpireEngine.assess(
        [
            EmpireAsset("a", "Business", 100, 1.0, 20, 0.12, 0.9, 0.9, 0.4),
            EmpireAsset("b", "IP", 50, 0.8, 10, 0.10, 0.8, 0.8, 0.3),
        ]
    )
    assert result.ownership_value == 140
    assert result.annual_cash_flow == 28
    assert result.stage is EmpireStage.COMPOUNDING
    assert "REINVEST_AND_COMPOUND" in result.priorities


def test_concentration_and_low_control_are_explicit_risks() -> None:
    result = EmpireEngine.assess(
        [EmpireAsset("a", "Single", 100, 0.2, 10, 0.03, 0.2, 0.4, 0.95)]
    )
    assert "INCREASE_ECONOMIC_OWNERSHIP" in result.priorities
    assert "INCREASE_STRATEGIC_CONTROL" in result.priorities
    assert "REDUCE_SINGLE_ASSET_CONCENTRATION" in result.priorities
