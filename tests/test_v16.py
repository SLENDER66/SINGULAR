from singular.empire import AgentRegistry, AgentSpec, AutopilotSupervisor, Event, EventType
from singular.models import Action
from singular.agents import Commander
from singular.v16_workforce import WorkforcePlanner, build_default_registry


def test_workforce_has_core_roles():
    reg = build_default_registry()
    assert 'COMMANDER' in reg.agents
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


def test_commander_produces_one_clear_next_move():
    actions = [
        Action(id='A1', name='Faire une action utile', impact=8, urgency=6, effort=2, risk=2, leverage=8, optionality=7, reversibility=9),
        Action(id='A2', name='Faire une tâche secondaire', impact=3, urgency=3, effort=4, risk=2, leverage=2, optionality=2, reversibility=9),
    ]
    brief = Commander().command('Améliorer la situation', actions)
    assert brief['mode'] == 'ACT'
    assert brief['priority']['id'] == 'A1'
    assert brief['next_move'] == 'Faire une action utile'
    assert brief['human_gate'] is False
    assert brief['objective'] == 'Améliorer la situation'


def test_commander_stops_when_blocked():
    brief = Commander().command('Avancer', [], blockers=['Information critique manquante'])
    assert brief['mode'] == 'BLOCKED'
    assert 'blocage' in brief['next_move'].lower()


def test_supervisor_escalates_missing_handler():
    reg = AgentRegistry(); reg.register(AgentSpec('X', 'x', ('research',), 1, None))
    s = AutopilotSupervisor(reg); run = s.create_run('research')
    assert s.route(run, 'research', {}) is None
    assert run.status == 'WAITING_HUMAN'


def test_event_audit():
    s = AutopilotSupervisor(build_default_registry()); s.events.publish(Event(EventType.USER, 'goal', {'x': 1}))
    assert len(s.audit) == 1
