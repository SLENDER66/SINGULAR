from singular.autopilot import ActionRequest, Autonomy
from singular.evals import evaluate_mission
from singular.mission_autopilot import Mission, MissionAutopilot, StepStatus


def test_autopilot_plans_but_never_executes_reversible_steps():
    auto = MissionAutopilot()
    contract = auto.bus
    # Use a minimal fake contract via manager.
    from singular.autopilot import MissionManager
    mm = MissionManager()
    c = mm.create_contract('X', 'Y', autonomy=Autonomy.EXECUTE_REVERSIBLE)
    a1 = ActionRequest('prepare', 'prepare', 2, 1, 9)
    a2 = ActionRequest('finish', 'finish', 2, 1, 9)
    auto.register_handler('prepare', lambda a: 'ok1')
    auto.register_handler('finish', lambda a: 'ok2')
    m = Mission('X', 'Y', c)
    auto.plan(m, [(a1, ()), (a2, ('prepare',))])
    auto.run(m)
    # MissionAutopilot.run no longer executes: orchestration decides what to
    # do next, never that something may be done. Every step is blocked
    # pending a ValidatedTrajectoryDecision.
    assert m.status == StepStatus.BLOCKED
    assert [step.status for step in m.steps] == [StepStatus.BLOCKED, StepStatus.BLOCKED]
    assert all("ValidatedTrajectoryDecision" in (step.error or "") for step in m.steps)
    # Nothing completed, because nothing ran.
    assert evaluate_mission(m).completion == 0.0


def test_autopilot_never_bypasses_governor_for_sensitive_step():
    from singular.autopilot import MissionManager
    mm = MissionManager()
    c = mm.create_contract('X', 'Y', autonomy=Autonomy.EXECUTE_AUTHORIZED)
    auto = MissionAutopilot()
    sensitive = ActionRequest('send', 'sensitive', 8, 1, 9, sensitive=True)
    called = []
    auto.register_handler('send', lambda a: called.append(True))
    m = Mission('X', 'Y', c)
    auto.plan(m, [(sensitive, ())])
    auto.run(m)
    assert m.status == StepStatus.BLOCKED
    assert called == []
