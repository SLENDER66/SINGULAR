import pytest

from singular.agent_orchestration import NextBestAction, WorkClass, WorkItem


def item(item_id, **kwargs):
    defaults = dict(
        title=item_id,
        work_class=WorkClass.CORRECTNESS,
        impact=5,
        confidence=1,
        urgency=5,
        strategic_value=5,
        effort_hours=1,
    )
    defaults.update(kwargs)
    return WorkItem(item_id, **defaults)


def test_next_best_action_prefers_high_value_per_effort():
    engine = NextBestAction()
    fast = item("fast", impact=7, strategic_value=7, effort_hours=1)
    slow = item("slow", impact=10, strategic_value=10, effort_hours=10)
    assert engine.rank((slow, fast))[0].id == "fast"


def test_revenue_blocker_gets_explicit_priority_bonus():
    engine = NextBestAction()
    normal = item("normal", impact=6, strategic_value=6)
    blocker = item("revenue", impact=6, strategic_value=6, blocks_revenue=True)
    assert engine.rank((normal, blocker))[0].id == "revenue"


def test_parallel_batch_is_bounded_and_deterministic():
    engine = NextBestAction()
    items = tuple(item(str(i), impact=i) for i in range(10))
    assert len(engine.next_batch(items)) == 4
    assert engine.next_batch(items) == engine.next_batch(tuple(reversed(items)))


def test_duplicate_ids_are_rejected():
    engine = NextBestAction()
    with pytest.raises(ValueError, match="unique"):
        engine.rank((item("same"), item("same")))


def test_non_finite_work_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        item("nan", impact=float("nan"))
