from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class EmpireStage(str, Enum):
    FOUNDATION = "FOUNDATION"
    CASH_FLOW = "CASH_FLOW"
    OWNERSHIP = "OWNERSHIP"
    COMPOUNDING = "COMPOUNDING"
    CONTROL = "CONTROL"
    INSTITUTION = "INSTITUTION"


@dataclass(frozen=True)
class EmpireAsset:
    """A productive asset evaluated by ownership, cash flow and strategic control."""

    id: str
    name: str
    value: float
    ownership: float
    annual_cash_flow: float
    growth_rate: float
    strategic_control: float
    durability: float
    concentration: float

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("asset id and name cannot be empty")
        for field_name, value in (
            ("value", self.value),
            ("annual_cash_flow", self.annual_cash_flow),
            ("growth_rate", self.growth_rate),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        for field_name, value in (
            ("ownership", self.ownership),
            ("strategic_control", self.strategic_control),
            ("durability", self.durability),
            ("concentration", self.concentration),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1")


@dataclass(frozen=True)
class EmpireAssessment:
    stage: EmpireStage
    productive_value: float
    ownership_value: float
    annual_cash_flow: float
    strategic_control: float
    concentration_risk: float
    score: float
    priorities: tuple[str, ...]


class EmpireEngine:
    """Measure whether wealth is becoming durable productive ownership.

    The engine does not equate a large balance sheet with an empire. It rewards
    assets that produce cash flow, appreciate, remain controlled and survive
    beyond the founder's direct labor. It is advisory only.
    """

    @staticmethod
    def assess(assets: list[EmpireAsset]) -> EmpireAssessment:
        if not assets:
            return EmpireAssessment(
                EmpireStage.FOUNDATION, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                ("BUILD_FIRST_PRODUCTIVE_ASSET",),
            )

        productive_value = sum(asset.value for asset in assets)
        ownership_value = sum(asset.value * asset.ownership for asset in assets)
        cash_flow = sum(asset.annual_cash_flow * asset.ownership for asset in assets)
        weighted_control = sum(asset.value * asset.strategic_control for asset in assets) / productive_value
        concentration = sum(asset.concentration * asset.value for asset in assets) / productive_value
        growth = sum(asset.value * asset.growth_rate for asset in assets) / productive_value
        durability = sum(asset.value * asset.durability for asset in assets) / productive_value

        score = (
            ownership_value * (1 + growth)
            + cash_flow
            + productive_value * weighted_control * durability
        ) / (1 + productive_value * concentration)
        score = round(score, 6)

        if productive_value == 0:
            stage = EmpireStage.FOUNDATION
        elif ownership_value <= 0:
            stage = EmpireStage.CASH_FLOW
        elif growth >= 0.15 and weighted_control >= 0.7:
            stage = EmpireStage.CONTROL
        elif growth >= 0.08 and durability >= 0.7:
            stage = EmpireStage.COMPOUNDING
        else:
            stage = EmpireStage.OWNERSHIP

        priorities: list[str] = []
        if ownership_value / productive_value < 0.5:
            priorities.append("INCREASE_ECONOMIC_OWNERSHIP")
        if cash_flow <= 0:
            priorities.append("BUILD_RECURRING_CASH_FLOW")
        if weighted_control < 0.6:
            priorities.append("INCREASE_STRATEGIC_CONTROL")
        if concentration > 0.7:
            priorities.append("REDUCE_SINGLE_ASSET_CONCENTRATION")
        if durability < 0.6:
            priorities.append("IMPROVE_DURABILITY_AND_SYSTEMIZATION")
        if not priorities and stage in {EmpireStage.COMPOUNDING, EmpireStage.CONTROL}:
            priorities.append("REINVEST_AND_COMPOUND")

        return EmpireAssessment(
            stage,
            round(productive_value, 6),
            round(ownership_value, 6),
            round(cash_flow, 6),
            round(weighted_control, 6),
            round(concentration, 6),
            score,
            tuple(priorities),
        )

    @staticmethod
    def strategic_layers() -> tuple[str, ...]:
        return (
            "CASH_FLOW: create reliable surplus",
            "OWNERSHIP: convert labor into equity and productive assets",
            "CONTROL: acquire durable strategic decision rights",
            "COMPOUNDING: reinvest surplus into higher-value productive assets",
            "SYSTEMIZATION: make the machine less dependent on founder time",
            "INSTITUTION: protect, govern and transmit the patrimony",
        )
