from singular.architecture_invariants import DEFAULT_INVARIANTS, InvariantSeverity


def test_default_invariants_are_unique_and_blocking():
    invariants = DEFAULT_INVARIANTS.all()
    assert len(invariants) == len({item.id for item in invariants})
    assert all(item.severity is InvariantSeverity.BLOCKING for item in invariants)


def test_core_invariants_exist():
    ids = {item.id for item in DEFAULT_INVARIANTS.all()}
    assert {
        "AUTH-001",
        "AUTH-002",
        "AUTH-003",
        "EXEC-001",
        "EXEC-002",
        "EXEC-003",
        "EXEC-004",
        "EXEC-005",
        "EXEC-006",
        "LEARN-001",
        "LEARN-002",
        "EPI-001",
        "AUDIT-001",
        "FAIL-001",
    } <= ids
