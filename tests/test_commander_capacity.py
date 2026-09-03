from singular.agents import Commander
from singular.models import Action
from singular.state import CapacitySnapshot


def test_commander_respects_capacity_limit():
    action = Action(name="Deep work", impact=8, urgency=5, effort=5, risk=1, reversibility=8)
    result = Commander().command(
        "Advance the mission",
        [action],
        capacity=CapacitySnapshot(0.5, 0.4, 0.0, 1.0),
        effort=0.2,
    )
    assert result["mode"] == "CAPACITY_LIMIT"
    assert result["capacity_recommendation"] == "DEFER_OR_DROP"
