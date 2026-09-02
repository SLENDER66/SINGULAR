from singular.autopilot import ActionRequest, Autonomy
from singular.mission_autopilot import MissionAutopilot, Mission, StepStatus
from singular.evals import evaluate_mission


def test_autopilot_executes_authorized_reversible_steps():
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
    assert m.status == StepStatus.DONE
    assert evaluate_mission(m).completion == 1.0


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
