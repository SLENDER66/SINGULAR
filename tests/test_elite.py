from singular.elite import EliteEngine, EliteScore


def test_elite_score_is_simple_and_measurable():
    score = EliteScore(1.0, 0.8, 0.9, 0.7, 0.6)
    assert score.total == 0.8
    assert score.weakest == 'learning'


def test_elite_review_targets_the_weakest_dimension():
    review = EliteEngine.review('STRATEGY', EliteScore(0.95, 0.95, 0.95, 0.5, 0.9))
    assert review.agent == 'STRATEGY'
    assert review.priority == 'calibration'
    assert 'outcomes' in review.directive.lower()


def test_elite_score_rejects_invalid_values():
    try:
        EliteScore(1.2, 0.8, 0.9, 0.7, 0.6).total
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid elite score must fail closed')
