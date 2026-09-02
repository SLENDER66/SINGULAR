from singular.tool_fabric import ToolFabric, ToolSpec
from singular.autopilot import MissionManager, Autonomy
from singular.cockpit import Cockpit


def test_autonomous_tool_requires_contract():
    fabric = ToolFabric()
    fabric.register(ToolSpec("safe", "safe action", risk=1, reversibility=9, handler=lambda: "ok"))
    try:
        fabric.execute_autonomous("safe")
        assert False
    except PermissionError:
        pass


def test_approved_tool_executes():
    fabric = ToolFabric()
    fabric.register(ToolSpec("email", "send email", risk=5, reversibility=3, requires_human=True, handler=lambda body: body))
    mission = MissionManager().create_contract("test", "send", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    action, decision = fabric.plan("email", "send", mission)
    assert decision.mode == Autonomy.ESCALATE
    aid = decision.approval_id
    fabric.bus.approve(aid)
    assert fabric.execute_approved(aid, "email", body="hello") == "hello"


def test_cockpit_shows_pending():
    mm = MissionManager()
    c = mm.create_contract("test", "x")
    from singular.autopilot import ActionRequest
    mm.route(ActionRequest("sensitive", "x", 5, 5, 3, sensitive=True), c.mission_id)
    snap = Cockpit(mm).snapshot()
    assert snap["human_load"] == 1
