from singular.agents import Commander
from singular.models import Action
from singular.state import CapacitySnapshot


def test_commander_recommends_scope_reduction_when_headroom_exists():
    action = Action(id="a1", name="Deep work", impact=8, urgency=5, leverage=7, effort=5, risk=1, reversibility=8)
    result = Commander().command(
        "Advance the mission",
        [action],
        capacity=CapacitySnapshot(0.5, 0.4, 0.0, 1.0),
        effort=0.2,
    )
    assert result["mode"] == "CAPACITY_LIMIT"
    assert result["capacity_recommendation"] == "REDUCE_SCOPE"
