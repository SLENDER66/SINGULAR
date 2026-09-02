from singular.engine import SingularEngine
from singular.models import Action, Decision

def test_high_leverage_action_wins():
    actions = [
        Action(id='1', name='high', impact=8, urgency=7, leverage=9, effort=3, risk=2, reversibility=9, optionality=9),
        Action(id='2', name='heavy', impact=9, urgency=6, leverage=5, effort=8, risk=4, reversibility=5, optionality=4),
    ]
    assert SingularEngine.rank_actions(actions)[0][0].name == 'high'

def test_bottleneck():
    assert SingularEngine.bottleneck({'A': 8, 'B': 3, 'C': 6}) == 'B'

def test_halt_for_high_consequence_irreversible_unknown():
    d = Decision(id='D', question='x', options=['a'], recommendation='a', confidence=.6, unknowns=['critical'])
    assessment = SingularEngine.decision_assessment(d, consequence=9, reversibility=2)
    assert assessment.halt is True

def test_reversible_low_consequence_does_not_halt():
    d = Decision(id='D', question='x', options=['a'], recommendation='a', confidence=.6, unknowns=['minor'])
    assessment = SingularEngine.decision_assessment(d, consequence=4, reversibility=8)
    assert assessment.halt is False
