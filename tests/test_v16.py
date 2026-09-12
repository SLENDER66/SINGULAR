from singular.agents import Commander
from singular.empire import (
    AgentRegistry,
    AgentSpec,
    AutopilotSupervisor,
    Event,
    EventType,
)
from singular.models import Action


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


def test_supervisor_blocks_instead_of_invoking_a_handler():
    """Routing selects an agent; it does not authorize one to act.

    The run used to end WAITING_HUMAN only when no handler existed, which meant
    a run with a handler was routed straight into it. AutopilotSupervisor.route
    is now observation only: it selects and records, then blocks pending a
    ValidatedTrajectoryDecision, whether or not a handler is present.
    """
    reg = AgentRegistry(); reg.register(AgentSpec('X', 'x', ('research',), 1, None))
    s = AutopilotSupervisor(reg); run = s.create_run('research')
    assert s.route(run, 'research', {}) is None
    assert run.status == 'BLOCKED'
    assert any('ValidatedTrajectoryDecision' in blocker for blocker in run.blockers)


def test_event_audit():
    reg = AgentRegistry(); reg.register(AgentSpec('X', 'x', ('research',), 1, None))
    s = AutopilotSupervisor(reg); s.events.publish(Event(EventType.USER, 'goal', {'x': 1}))
    assert len(s.audit) == 1
