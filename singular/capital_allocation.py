from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from math import isfinite

from .wealth_engine import WealthOpportunity


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
        if self.capital_required < 0 or not isfinite(self.capital_required):
            raise ValueError("capital_required must be finite and non-negative")
        if self.capacity_required < 0 or not isfinite(self.capacity_required):
            raise ValueError("capacity_required must be finite and non-negative")


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
    """Select a bounded capital portfolio under explicit safety constraints.

    The engine separates protection from deployment and only recommends an
    allocation. It does not invest, borrow, transfer money or authorize effects.
    Exhaustive search is used for small bounded portfolios so an exact result
    can be honestly reported. A later branch-and-bound implementation can
    preserve this contract for larger candidate sets.
    """

    @staticmethod
    def _utility(candidate: AllocationCandidate) -> float:
        from .wealth_engine import WealthEngine

        return WealthEngine.assess(candidate.opportunity).score

    @classmethod
    def optimize(
        cls,
        candidates: list[AllocationCandidate],
        available_capital: float,
        protected_capital: float,
        risk_budget: float,
        max_positions: int,
        capacity_budget: float = float("inf"),
    ) -> CapitalAllocation:
        for name, value in (
            ("available_capital", available_capital),
            ("protected_capital", protected_capital),
            ("risk_budget", risk_budget),
        ):
            if value < 0 or not isfinite(value):
                raise ValueError(f"{name} must be finite and non-negative")
        if capacity_budget < 0 or (not isfinite(capacity_budget) and capacity_budget != float("inf")):
            raise ValueError("capacity_budget must be non-negative and finite, or inf")
        if protected_capital > available_capital:
            raise ValueError("protected_capital cannot exceed available_capital")
        if max_positions < 0:
            raise ValueError("max_positions cannot be negative")

        ordered = tuple(sorted(candidates, key=lambda item: item.opportunity.id))
        if len({item.opportunity.id for item in ordered}) != len(ordered):
            raise ValueError("candidate opportunity ids must be unique")
        investable = available_capital - protected_capital
        best: tuple[float, tuple[str, ...], float, float, float] | None = None

        for count in range(min(max_positions, len(ordered)) + 1):
            for combo in combinations(ordered, count):
                capital = sum(item.capital_required for item in combo)
                risk = sum(item.opportunity.downside * item.opportunity.probability for item in combo)
                capacity = sum(item.capacity_required for item in combo)
                if capital > investable or risk > risk_budget or capacity > capacity_budget:
                    continue
                utility = sum(cls._utility(item) for item in combo)
                ids = tuple(item.opportunity.id for item in combo)
                if best is None or utility > best[0] or (utility == best[0] and ids < best[1]):
                    best = (utility, ids, capital, risk, capacity)

        if best is None:
            best = (0.0, (), 0.0, 0.0, 0.0)

        _, ids, capital, risk, capacity = best
        selected = {item.opportunity.id: item for item in ordered if item.opportunity.id in ids}
        rationale = ["PROTECTION_RESERVE_FIRST", "RECOMMENDATION_ONLY"]
        rationale.append("SELECTED_BY_RISK_ADJUSTED_WEALTH_UTILITY" if ids else "NO_CANDIDATE_FITS_CONSTRAINTS")

        return CapitalAllocation(
            candidate_ids=ids,
            protected_capital=round(protected_capital, 6),
            unallocated_capital=round(investable - capital, 6),
            expected_wealth_delta=round(sum(
                selected[item_id].opportunity.expected_wealth_delta
                * selected[item_id].opportunity.probability
                for item_id in ids
            ), 6),
            risk_exposure=round(risk, 6),
            capacity_used=round(capacity, 6),
            method="EXHAUSTIVE_EXACT",
            search_complete=True,
            rationale=tuple(rationale),
        )
