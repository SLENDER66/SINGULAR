from singular.empire import AgentRegistry, AgentSpec, AutopilotSupervisor, Event, EventType
from singular.v16_workforce import WorkforcePlanner, build_default_registry


def test_workforce_has_core_roles():
    reg = build_default_registry()
    assert 'COMMANDER' not in reg.agents
    assert 'RED_TEAM' in reg.agents and 'SYSTEM_ARCHITECT' in reg.agents
    assert 'MENTAL' in reg.agents and 'PRESENCE' in reg.agents


def test_human_specialists_have_distinct_capabilities():
    reg = build_default_registry()
    mental = reg.agents['MENTAL']
    presence = reg.agents['PRESENCE']
    assert 'mental_state' in mental.capabilities
    assert 'recovery' in mental.capabilities
    assert 'physical' in presence.capabilities
    assert 'presence' in presence.capabilities
    assert set(mental.capabilities).isdisjoint(presence.capabilities)


def test_planner_selects_specialists():
    reg = build_default_registry(); plan = WorkforcePlanner(reg).plan(['research', 'finance', 'red_team'])
    assert set(plan.selected) >= {'INTELLIGENCE', 'FINANCE', 'RED_TEAM'}
    assert plan.missing_capabilities == []


def test_planner_selects_human_specialists():
    reg = build_default_registry(); plan = WorkforcePlanner(reg).plan(['mental_state', 'physical', 'communication'])
    assert set(plan.selected) == {'MENTAL', 'PRESENCE'}
    assert plan.missing_capabilities == []


def test_supervisor_escalates_missing_handler():
    reg = AgentRegistry(); reg.register(AgentSpec('X', 'x', ('research',), 1, None))
    s = AutopilotSupervisor(reg); run = s.create_run('research')
    assert s.route(run, 'research', {}) is None
    assert run.status == 'WAITING_HUMAN'


def test_event_audit():
    s = AutopilotSupervisor(build_default_registry()); s.events.publish(Event(EventType.USER, 'goal', {'x': 1}))
    assert len(s.audit) == 1
