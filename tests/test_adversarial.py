from singular.adversarial import AttackClass, AttackSeverity, AdversarialEngine
from singular.authority import AgentPower, AuthorityProtocol


def test_authority_adversarial_suite_is_fail_closed() -> None:
    report = AdversarialEngine.authority_suite()

    assert report.passed is True
    assert report.critical_failures == 0
    assert report.coverage == 1.0
    assert all(finding.passed for finding in report.findings)


def test_authority_invariants_cover_all_non_human_execution_paths() -> None:
    non_execution_agents = (
        "INTELLIGENCE",
        "STRATEGY",
        "SPECIALIST",
        "RED_TEAM",
        "COMMANDER",
        "SYSTEM_ARCHITECT",
    )
    for agent in non_execution_agents:
        assert AuthorityProtocol.can(agent, AgentPower.EXECUTE) is False
        assert AuthorityProtocol.can(agent, AgentPower.AUTHORIZE) is False
        assert AuthorityProtocol.can(agent, AgentPower.HUMAN_FINAL) is False


def test_adversarial_suite_contains_critical_controls() -> None:
    report = AdversarialEngine.authority_suite()
    critical_ids = {
        finding.attack_id
        for finding in report.findings
        if finding.severity is AttackSeverity.CRITICAL
    }

    assert critical_ids == {"AUTH-001", "AUTH-002", "AUTH-003", "AUTH-005", "AUTH-006"}


def test_full_adversarial_suite_is_fail_closed_and_covers_multiple_attack_classes() -> None:
    report = AdversarialEngine.full_suite()

    assert report.passed is True
    assert report.critical_failures == 0
    assert report.coverage == 1.0
    assert {attack_class for attack_class in report.classes} >= {
        AttackClass.AUTH,
        AttackClass.AUDIT,
        AttackClass.REPLAY,
        AttackClass.LEARN,
    }
    assert len(report.findings) >= 10
