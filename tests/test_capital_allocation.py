import pytest
from singular.capital_allocation import AllocationBucket, AllocationCandidate, CapitalAllocationEngine
from singular.wealth_engine import WealthOpportunity


def candidate(id: str, *, cost: float = 1.0, ownership: float = 0.8, compounding: float = 0.8, downside: float = 0.1) -> AllocationCandidate:
    return AllocationCandidate(WealthOpportunity(id=id, expected_wealth_delta=100, probability=0.8, downside=downside,
        cost=cost, time=1, ownership=ownership, compounding=compounding, optionality=0.8, reversibility=0.9),
        AllocationBucket.OWNERSHIP, cost)


def test_protection_reserve_is_never_allocated() -> None:
    result = CapitalAllocationEngine.optimize([candidate("a", cost=6)], 10, 7, 10, 1)
    assert result.protected_capital == 7
    assert result.candidate_ids == ()
    assert result.unallocated_capital == 3


def test_best_feasible_candidate_is_selected() -> None:
    result = CapitalAllocationEngine.optimize([candidate("b", cost=4), candidate("a", cost=2)], 10, 2, 10, 1)
    assert result.candidate_ids == ("a",)
    assert result.search_complete is True
    assert result.method == "BRANCH_AND_BOUND_EXACT"


def test_high_downside_can_be_excluded_by_risk_budget() -> None:
    result = CapitalAllocationEngine.optimize([candidate("safe", downside=0.1), candidate("risky", downside=10)], 10, 0, 1, 1)
    assert result.candidate_ids == ("safe",)


def test_ties_are_deterministic() -> None:
    first = CapitalAllocationEngine.optimize([candidate("b"), candidate("a")], 10, 0, 10, 1)
    second = CapitalAllocationEngine.optimize([candidate("a"), candidate("b")], 10, 0, 10, 1)
    assert first.candidate_ids == second.candidate_ids == ("a",)


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        CapitalAllocationEngine.optimize([candidate("a"), candidate("a")], 10, 0, 10, 2)


def test_node_budget_is_explicitly_bounded() -> None:
    result = CapitalAllocationEngine.optimize([candidate(chr(97 + i)) for i in range(12)], 100, 0, 100, 6, max_nodes=2)
    assert result.search_complete is False
    assert result.method == "BRANCH_AND_BOUND_BOUNDED"
