from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .cashflow_engine import CashflowAssessment, CashflowOpportunity, RapidCashEngine, RapidCashObjective


@dataclass(frozen=True)
class RapidWealthSprint:
    target_cash: float
    horizon_days: int
    selected_opportunities: tuple[CashflowAssessment, ...]
    expected_cash: float
    target_gap: float
    required_human_review: bool
    rules: tuple[str, ...]


class RapidWealthEngine:
    """Connect immediate cash generation to durable wealth creation.

    This layer recommends and sequences opportunities only. It never executes
    financial, contractual, account, or other sensitive external actions.
    """

    @staticmethod
    def build_sprint(
        opportunities: list[CashflowOpportunity],
        objective: RapidCashObjective,
        *,
        max_parallel_tests: int = 3,
    ) -> RapidWealthSprint:
        if max_parallel_tests <= 0:
            raise ValueError("max_parallel_tests must be positive")
        ranked = RapidCashEngine.build_sprint(
            opportunities, objective, max_parallel_tests=max_parallel_tests
        )
        expected_cash = round(sum(item.expected_value for item in ranked if item.expected_value > 0), 6)
        return RapidWealthSprint(
            target_cash=objective.target_cash,
            horizon_days=objective.horizon_days,
            selected_opportunities=ranked,
            expected_cash=expected_cash,
            target_gap=round(max(objective.target_cash - expected_cash, 0.0), 6),
            required_human_review=any(item.human_review_required for item in ranked),
            rules=(
                "CASH_FIRST_BUT_NOT_CASH_ONLY",
                "NO_NEGATIVE_EXPECTED_VALUE",
                "PREFER_FAST_RECURRING_OR_OWNED_PATHS",
                "PRESERVE_DOWN_SIDE_AND_OPTIONALITY",
                "REINVEST_SURPLUS_INTO_CAPACITY_AND_OWNERSHIP",
            ),
        )

    @staticmethod
    def validate_objective(objective: RapidCashObjective) -> None:
        if not isfinite(objective.target_cash) or objective.target_cash <= 0:
            raise ValueError("target_cash must be finite and positive")
        if objective.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")

    @staticmethod
    def next_stage() -> tuple[str, ...]:
        return (
            "PROTECT_SURVIVAL",
            "GENERATE_CASH",
            "BUILD_RECURRING_INCOME",
            "INCREASE_EARNING_POWER",
            "ACQUIRE_OWNERSHIP",
            "ALLOCATE_AND_COMPOUND",
            "SYSTEMIZE",
            "BUILD_INSTITUTION",
        )
