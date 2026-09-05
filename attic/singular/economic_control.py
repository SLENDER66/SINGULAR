from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .capital_allocation import AllocationCandidate, CapitalAllocation, CapitalAllocationEngine
from .cashflow_engine import CashflowOpportunity, RapidCashObjective
from .economic_sequence import EconomicSequence, EconomicSequenceEngine, EconomicStage, EconomicStep
from .empire_engine import EmpireAssessment, EmpireAsset, EmpireEngine
from .generational import GenerationalCharter, GenerationalEngine, GenerationalReadiness
from .patrimony_engine import FailureConversion, FailureRecord, PatrimonyAssessment, PatrimonyEngine
from .rapid_wealth import RapidWealthEngine, RapidWealthSprint
from .wealth_engine import WealthAssessment, WealthEngine, WealthObjective, WealthOpportunity


class EconomicPlanStatus(str, Enum):
    READY = "READY"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class EconomicControlPlan:
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
    economic_sequence: EconomicSequence


class EconomicControlPlane:
    REQUIRED_GENERATIONAL_METRICS = (
        "capital_protection",
        "founder_independence",
        "institutional_resilience",
    )

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
        economic_sequence_steps: list[EconomicStep] | None = None,
        completed_economic_stages: tuple[EconomicStage, ...] = (),
        max_allocation_nodes: int = 100_000,
    ) -> EconomicControlPlan:
        EconomicControlPlane._validate_capital(
            available_capital, protected_capital, risk_budget, capacity_budget
        )
        if max_allocation_positions < 0:
            raise ValueError("max_allocation_positions must be non-negative")
        missing = tuple(
            key
            for key in EconomicControlPlane.REQUIRED_GENERATIONAL_METRICS
            if key not in generational_metrics
        )
        if missing:
            raise ValueError(f"missing generational metrics: {', '.join(missing)}")
        for key in EconomicControlPlane.REQUIRED_GENERATIONAL_METRICS:
            metric_value = generational_metrics[key]
            if not isfinite(metric_value) or not 0 <= metric_value <= 1:
                raise ValueError(
                    f"generational metric {key} must be finite and within [0, 1]"
                )

        failure_items: list[FailureRecord] = failures or []
        conversions: tuple[FailureConversion, ...] = tuple(
            PatrimonyEngine.convert_failure(failure_item)
            for failure_item in failure_items
        )
        rapid_cash = RapidWealthEngine.build_sprint(
            cashflow_opportunities,
            rapid_cash_objective,
            max_parallel_tests=max_parallel_cash_tests,
        )
        wealth_assessments = WealthEngine.rank(wealth_opportunities, wealth_objective)
        allocation = CapitalAllocationEngine.optimize(
            allocation_candidates,
            available_capital=available_capital,
            protected_capital=protected_capital,
            risk_budget=risk_budget,
            capacity_budget=capacity_budget,
            max_positions=max_allocation_positions,
            objective=wealth_objective,
            max_nodes=max_allocation_nodes,
        )
        empire = EmpireEngine.assess(empire_assets)
        patrimony_assessment = PatrimonyEngine.assess(
            generations=int(patrimony["generations"]),
            ownership_continuity=float(patrimony["ownership_continuity"]),
            governance=float(patrimony["governance"]),
            systemization=float(patrimony["systemization"]),
            succession=float(patrimony["succession"]),
            resilience=float(patrimony["resilience"]),
        )
        generational = GenerationalEngine.assess(
            generational_charter,
            capital_protection=generational_metrics["capital_protection"],
            founder_independence=generational_metrics["founder_independence"],
            institutional_resilience=generational_metrics["institutional_resilience"],
        )
        sequence_steps = (
            economic_sequence_steps
            if economic_sequence_steps is not None
            else EconomicControlPlane._derive_sequence_steps(
                cashflow_opportunities,
                rapid_cash,
                wealth_opportunities,
                wealth_assessments,
            )
        )
        lesson_ids = tuple(item.failure_id for item in conversions if item.learning_asset)
        economic_sequence = EconomicSequenceEngine.plan(
            sequence_steps,
            available_capacity=capacity_budget,
            completed_stages=completed_economic_stages,
            failure_lesson_ids=lesson_ids,
        )

        blockers: list[str] = []
        warnings: list[str] = []
        if rapid_cash.target_gap > 0:
            warnings.append("RAPID_CASH_TARGET_GAP")
        if allocation.unallocated_capital > 0:
            warnings.append("CAPITAL_NOT_FULLY_ALLOCATED")
        if not allocation.search_complete:
            warnings.append("CAPITAL_ALLOCATION_SEARCH_BOUNDED")
        if not generational.ready:
            warnings.extend(generational.priorities)
        if patrimony_assessment.priorities:
            warnings.extend(patrimony_assessment.priorities)
        if not cashflow_opportunities and not wealth_opportunities:
            blockers.append("NO_ECONOMIC_OPPORTUNITIES")
        if rapid_cash.target_gap == rapid_cash.target_cash:
            blockers.append("NO_POSITIVE_EXPECTED_CASH_PATH")
        status = (
            EconomicPlanStatus.BLOCKED
            if blockers
            else EconomicPlanStatus.REVIEW
            if warnings
            else EconomicPlanStatus.READY
        )
        next_actions = EconomicControlPlane._next_actions(
            rapid_cash,
            wealth_assessments,
            allocation,
            empire,
            patrimony_assessment,
            generational,
            economic_sequence,
        )
        return EconomicControlPlan(
            status,
            rapid_cash,
            wealth_assessments,
            allocation,
            empire,
            patrimony_assessment,
            generational,
            conversions,
            tuple(dict.fromkeys(blockers)),
            tuple(dict.fromkeys(warnings)),
            next_actions,
            economic_sequence,
        )

    @staticmethod
    def _derive_sequence_steps(
        cash: list[CashflowOpportunity],
        rapid: RapidWealthSprint,
        opportunities: list[WealthOpportunity],
        assessments: tuple[WealthAssessment, ...],
    ) -> list[EconomicStep]:
        cash_by_id = {cash_item.id: cash_item for cash_item in cash}
        selected = {item.opportunity_id for item in rapid.selected_opportunities}
        steps: list[EconomicStep] = []
        for cash_assessment in rapid.selected_opportunities:
            cash_item = cash_by_id[cash_assessment.opportunity_id]
            steps.append(
                EconomicStep(
                    cash_item.id,
                    EconomicStage.CASH,
                    expected_cash=cash_item.expected_cash,
                    probability=cash_item.probability,
                    risk=10.0 * (1.0 - cash_item.reversibility),
                    capacity_required=max(cash_item.time_to_cash_hours / 24.0, 0.0),
                    reversibility=10.0 * cash_item.reversibility,
                    ownership_value=10.0 * cash_item.ownership_score,
                    compounding_value=10.0 * cash_item.recurrence_score,
                )
            )
        wealth_by_id = {wealth_item.id: wealth_item for wealth_item in opportunities}
        for wealth_assessment in assessments:
            if wealth_assessment.opportunity_id in selected:
                continue
            wealth_item = wealth_by_id[wealth_assessment.opportunity_id]
            steps.append(
                EconomicStep(
                    wealth_item.id,
                    EconomicStage.OWNERSHIP
                    if wealth_item.ownership >= 0.5
                    else EconomicStage.CAPITAL,
                    expected_value=max(wealth_item.expected_wealth_delta, 0.0),
                    probability=wealth_item.probability,
                    risk=min(wealth_item.downside * 10.0, 10.0),
                    capacity_required=wealth_item.time,
                    reversibility=10.0 * wealth_item.reversibility,
                    ownership_value=10.0 * wealth_item.ownership,
                    compounding_value=10.0 * wealth_item.compounding,
                )
            )
        return steps

    @staticmethod
    def _validate_capital(
        available: float, protected: float, risk: float, capacity: float
    ) -> None:
        for name, value in (
            ("available_capital", available),
            ("protected_capital", protected),
            ("risk_budget", risk),
            ("capacity_budget", capacity),
        ):
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
        sequence: EconomicSequence,
    ) -> tuple[str, ...]:
        actions: list[str] = []
        if sequence.steps:
            actions.append(f"FOLLOW_ECONOMIC_SEQUENCE:{sequence.steps[0].id}")
        elif rapid.selected_opportunities:
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
