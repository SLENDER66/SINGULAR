from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .cashflow_engine import CashflowAssessment, CashflowOpportunity, RapidCashEngine, RapidCashObjective
from .capital_allocation import AllocationCandidate, CapitalAllocation, CapitalAllocationEngine
from .empire_engine import EmpireAssessment, EmpireAsset, EmpireEngine
from .generational import GenerationalCharter, GenerationalEngine, GenerationalReadiness
from .patrimony_engine import FailureConversion, FailureRecord, PatrimonyAssessment, PatrimonyEngine
from .wealth_engine import WealthAssessment, WealthEngine, WealthObjective, WealthOpportunity
from .rapid_wealth import RapidWealthEngine, RapidWealthSprint


class EconomicPlanStatus(str, Enum):
    READY = "READY"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class EconomicControlPlan:
    """Immutable economic control-plane output: recommendation, never execution."""

    status: EconomicPlanStatus
    rapid_cash: RapidWealthSprint
    wealth_assessments: tuple[WealthAssessment, ...]
    allocation: CapitalAllocation
    empire: EmpireAssessment
    patrimony: PatrimonyAssessment
    generational: GenerationalReadiness
    failure_conversions: tuple[FailureConversion, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    next_actions: tuple[str, ...]


class EconomicControlPlane:
    """Coordinate cash, wealth, ownership, patrimony and succession decisions."""

    @staticmethod
    def build(
        *,
        cashflow_opportunities: list[CashflowOpportunity],
        rapid_cash_objective: RapidCashObjective,
        wealth_opportunities: list[WealthOpportunity],
        wealth_objective: WealthObjective,
        allocation_candidates: list[AllocationCandidate],
        available_capital: float,
        protected_capital: float,
        risk_budget: float,
        capacity_budget: float,
        empire_assets: list[EmpireAsset],
        patrimony: dict[str, float | int],
        generational_charter: GenerationalCharter,
        generational_metrics: dict[str, float],
        failures: list[FailureRecord] | None = None,
        max_parallel_cash_tests: int = 3,
        max_allocation_positions: int = 3,
    ) -> EconomicControlPlan:
        EconomicControlPlane._validate_capital(available_capital, protected_capital, risk_budget, capacity_budget)
        if max_allocation_positions < 0:
            raise ValueError("max_allocation_positions must be non-negative")

        rapid_cash = RapidWealthEngine.build_sprint(
            cashflow_opportunities,
            rapid_cash_objective,
            max_parallel_tests=max_parallel_cash_tests,
        )
        wealth_assessments = WealthEngine.rank(wealth_opportunities)
        allocation = CapitalAllocationEngine.optimize(
            allocation_candidates,
            available_capital=available_capital,
            protected_capital=protected_capital,
            risk_budget=risk_budget,
            capacity_budget=capacity_budget,
            max_positions=max_allocation_positions,
        )
        empire = EmpireEngine.assess(empire_assets)
        patrimony_assessment = PatrimonyEngine.assess(**patrimony)
        generational = GenerationalEngine.assess(
            generational_charter,
            capital_protection=generational_metrics["capital_protection"],
            founder_independence=generational_metrics["founder_independence"],
            institutional_resilience=generational_metrics["institutional_resilience"],
        )
        conversions = tuple(PatrimonyEngine.convert_failure(item) for item in (failures or []))

        blockers: list[str] = []
        warnings: list[str] = []
        if rapid_cash.target_gap > 0:
            warnings.append("RAPID_CASH_TARGET_GAP")
        if any(item.action.value == "HUMAN_REVIEW" for item in rapid_cash.selected_opportunities):
            warnings.append("RAPID_CASH_HUMAN_REVIEW")
        if allocation.unallocated_capital > 0:
            warnings.append("CAPITAL_NOT_FULLY_ALLOCATED")
        if not generational.ready:
            warnings.extend(generational.priorities)
        if patrimony.priorities:
            warnings.extend(patrimony.priorities)

        if not cashflow_opportunities and not wealth_opportunities:
            blockers.append("NO_ECONOMIC_OPPORTUNITIES")
        if rapid_cash.target_gap == rapid_cash.target_cash:
            blockers.append("NO_POSITIVE_EXPECTED_CASH_PATH")

        status = EconomicPlanStatus.BLOCKED if blockers else EconomicPlanStatus.REVIEW if warnings else EconomicPlanStatus.READY
        next_actions = EconomicControlPlane._next_actions(rapid_cash, wealth_assessments, allocation, empire, patrimony_assessment, generational)
        return EconomicControlPlan(
            status=status,
            rapid_cash=rapid_cash,
            wealth_assessments=wealth_assessments,
            allocation=allocation,
            empire=empire,
            patrimony=patrimony_assessment,
            generational=generational,
            failure_conversions=conversions,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            next_actions=next_actions,
        )

    @staticmethod
    def _validate_capital(available: float, protected: float, risk: float, capacity: float) -> None:
        for name, value in (("available_capital", available), ("protected_capital", protected), ("risk_budget", risk), ("capacity_budget", capacity)):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if protected > available:
            raise ValueError("protected_capital cannot exceed available_capital")

    @staticmethod
    def _next_actions(
        rapid: RapidWealthSprint,
        wealth: tuple[WealthAssessment, ...],
        allocation: CapitalAllocation,
        empire: EmpireAssessment,
        patrimony: PatrimonyAssessment,
        generational: GenerationalReadiness,
    ) -> tuple[str, ...]:
        actions: list[str] = []
        if rapid.selected_opportunities:
            actions.append("EXECUTE_ONLY_AUTHORIZED_RAPID_CASH_TESTS")
        else:
            actions.append("SOURCE_NEW_FAST_CASH_OPPORTUNITIES")
        if wealth:
            actions.append("REVIEW_TOP_RISK_ADJUSTED_WEALTH_OPPORTUNITIES")
        if allocation.candidate_ids:
            actions.append("REVIEW_CAPITAL_ALLOCATION")
        if "BUILD_OWNERSHIP" in empire.priorities:
            actions.append("INCREASE_PRODUCTIVE_OWNERSHIP")
        if patrimony.priorities:
            actions.append(patrimony.priorities[0])
        if not generational.ready:
            actions.append(generational.priorities[0])
        return tuple(dict.fromkeys(actions))
