import pytest

from singular.state import CapacityEngine, CapacitySnapshot, StateDimension, StateObservation


def test_state_observation_is_bounded():
    with pytest.raises(ValueError):
        StateObservation(StateDimension.ENERGY, 1.1)
    with pytest.raises(ValueError):
        StateObservation(StateDimension.FOCUS, 0.5, confidence=-0.1)


def test_empty_state_is_conservative():
    snapshot = CapacityEngine.snapshot([])
    assert snapshot.headroom == 0
    assert CapacityEngine.recommendation(snapshot, 0.1) == "CLARIFY_STATE"


def test_capacity_prevents_overload():
    observations = [
        StateObservation(StateDimension.CAPACITY, 0.8, 0.9),
        StateObservation(StateDimension.ENERGY, 0.8, 0.9),
        StateObservation(StateDimension.FOCUS, 0.8, 0.9),
    ]
    snapshot = CapacityEngine.snapshot(observations)
    assert snapshot.headroom == 0.4
    assert CapacityEngine.can_absorb(snapshot, 0.3)
    assert not CapacityEngine.can_absorb(snapshot, 0.5)
    assert CapacityEngine.recommendation(snapshot, 0.5) == "REDUCE_SCOPE"


def test_low_confidence_state_requires_clarification():
    snapshot = CapacitySnapshot(0.9, 0.1, 0.0, 0.4)
    assert CapacityEngine.recommendation(snapshot, 0.1) == "CLARIFY_STATE"
