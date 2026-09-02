from singular.empire import AgentRegistry, AgentSpec, AutopilotSupervisor, Event, EventType
from singular.v16_workforce import build_default_registry, WorkforcePlanner

def test_workforce_has_core_roles():
    reg = build_default_registry()
    assert 'COMMANDER' not in reg.agents
    assert 'RED_TEAM' in reg.agents and 'SYSTEM_ARCHITECT' in reg.agents

def test_planner_selects_specialists():
    reg = build_default_registry(); plan = WorkforcePlanner(reg).plan(['research','finance','red_team'])
    assert set(plan.selected) >= {'INTELLIGENCE','FINANCE','RED_TEAM'}
    assert plan.missing_capabilities == []

def test_supervisor_escalates_missing_handler():
    reg = AgentRegistry(); reg.register(AgentSpec('X','x',('research',),1,None))
    s = AutopilotSupervisor(reg); run = s.create_run('research')
    assert s.route(run,'research',{}) is None
    assert run.status == 'WAITING_HUMAN'

def test_event_audit():
    s = AutopilotSupervisor(build_default_registry()); s.events.publish(Event(EventType.USER,'goal',{'x':1}))
    assert len(s.audit) == 1
