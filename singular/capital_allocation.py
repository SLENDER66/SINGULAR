from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from .wealth_engine import WealthEngine, WealthObjective, WealthOpportunity


class AllocationBucket(str, Enum):
    PROTECTION = "PROTECTION"
    EARNING_POWER = "EARNING_POWER"
    OWNERSHIP = "OWNERSHIP"
    INVESTMENT = "INVESTMENT"
    OPTION = "OPTION"


@dataclass(frozen=True)
class AllocationCandidate:
    """A capital deployment candidate; never an instruction to transact."""
    opportunity: WealthOpportunity
    bucket: AllocationBucket
    capital_required: float
    capacity_required: float = 0.0

    def __post_init__(self) -> None:
        if self.capital_required < 0 or not isfinite(self.capital_required): raise ValueError("capital_required must be finite and non-negative")
        if self.capacity_required < 0 or not isfinite(self.capacity_required): raise ValueError("capacity_required must be finite and non-negative")


@dataclass(frozen=True)
class CapitalAllocation:
    candidate_ids: tuple[str, ...]
    protected_capital: float
    unallocated_capital: float
    expected_wealth_delta: float
    risk_exposure: float
    capacity_used: float
    method: str
    search_complete: bool
    rationale: tuple[str, ...]


class CapitalAllocationEngine:
    """Exact branch-and-bound allocation with an explicit node budget."""

    @staticmethod
    def _utility(candidate: AllocationCandidate, objective: WealthObjective | None = None) -> float:
        return WealthEngine.assess(candidate.opportunity, objective).score

    @classmethod
    def optimize(cls, candidates: list[AllocationCandidate], available_capital: float, protected_capital: float,
                 risk_budget: float, max_positions: int, capacity_budget: float = float("inf"),
                 objective: WealthObjective | None = None, max_nodes: int = 100_000) -> CapitalAllocation:
        for name, value in (("available_capital", available_capital), ("protected_capital", protected_capital), ("risk_budget", risk_budget)):
            if value < 0 or not isfinite(value): raise ValueError(f"{name} must be finite and non-negative")
        if capacity_budget < 0 or (not isfinite(capacity_budget) and capacity_budget != float("inf")): raise ValueError("capacity_budget must be non-negative and finite, or inf")
        if max_positions < 0: raise ValueError("max_positions cannot be negative")
        if max_nodes <= 0: raise ValueError("max_nodes must be positive")
        if protected_capital > available_capital: raise ValueError("protected_capital cannot exceed available_capital")
        ordered = tuple(sorted(candidates, key=lambda item: item.opportunity.id))
        if len({item.opportunity.id for item in ordered}) != len(ordered): raise ValueError("candidate opportunity ids must be unique")

        scored = tuple((cls._utility(item, objective), item) for item in ordered)
        search_order = tuple(sorted(scored, key=lambda pair: (-pair[0], pair[1].opportunity.id)))
        suffix_positive = [0.0] * (len(search_order) + 1)
        for i in range(len(search_order) - 1, -1, -1): suffix_positive[i] = suffix_positive[i + 1] + max(search_order[i][0], 0.0)
        investable = available_capital - protected_capital
        best: tuple[float, tuple[str, ...], float, float, float] = (0.0, (), 0.0, 0.0, 0.0)
        nodes = 0
        complete = True

        def visit(index: int, ids: tuple[str, ...], utility: float, capital: float, risk: float, capacity: float) -> None:
            nonlocal best, nodes, complete
            if nodes >= max_nodes:
                complete = False
                return
            nodes += 1
            if utility + suffix_positive[index] < best[0]: return
            if utility > best[0] or (utility == best[0] and ids < best[1]): best = (utility, ids, capital, risk, capacity)
            if index >= len(search_order) or len(ids) >= max_positions: return
            score, candidate = search_order[index]
            c = candidate.capital_required
            r = candidate.opportunity.downside * candidate.opportunity.probability
            cap = candidate.capacity_required
            if capital + c <= investable and risk + r <= risk_budget and capacity + cap <= capacity_budget:
                visit(index + 1, ids + (candidate.opportunity.id,), utility + score, capital + c, risk + r, capacity + cap)
            if nodes < max_nodes: visit(index + 1, ids, utility, capital, risk, capacity)
            else: complete = False

        visit(0, (), 0.0, 0.0, 0.0, 0.0)
        _, ids, capital, risk, capacity = best
        selected = {item.opportunity.id: item for item in ordered if item.opportunity.id in ids}
        method = "BRANCH_AND_BOUND_EXACT" if complete else "BRANCH_AND_BOUND_BOUNDED"
        rationale = ("PROTECTION_RESERVE_FIRST", "RECOMMENDATION_ONLY",
                     "SELECTED_BY_RISK_ADJUSTED_WEALTH_UTILITY" if ids else "NO_CANDIDATE_FITS_CONSTRAINTS")
        return CapitalAllocation(ids, round(protected_capital, 6), round(investable - capital, 6),
            round(sum(selected[x].opportunity.expected_wealth_delta * selected[x].opportunity.probability for x in ids), 6),
            round(risk, 6), round(capacity, 6), method, complete, rationale)
