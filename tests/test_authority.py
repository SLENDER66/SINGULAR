import pytest

from singular.authority import AgentPower, AuthorityProtocol, ConflictType


def test_advice_authority_cannot_execute():
    assert not AuthorityProtocol.can("COMMANDER", AgentPower.EXECUTE)
    assert not AuthorityProtocol.can("RED_TEAM", AgentPower.AUTHORIZE)
    assert not AuthorityProtocol.can("SYSTEM_ARCHITECT", AgentPower.AUTHORIZE)


def test_governor_authorizes_but_does_not_execute():
    assert AuthorityProtocol.can("GOVERNOR", AgentPower.AUTHORIZE)
    assert not AuthorityProtocol.can("GOVERNOR", AgentPower.EXECUTE)


def test_execution_agent_cannot_authorize():
    with pytest.raises(PermissionError, match="cannot exercise authorize"):
        AuthorityProtocol.require("EXECUTION", AgentPower.AUTHORIZE)


def test_system_architect_cannot_self_approve():
    with pytest.raises(PermissionError, match="cannot exercise authorize"):
        AuthorityProtocol.require("SYSTEM_ARCHITECT", AgentPower.AUTHORIZE)


def test_conflict_resolution_is_deterministic_and_non_executing():
    for conflict in ConflictType:
        resolution = AuthorityProtocol.resolve(conflict)
        assert resolution.authority
        assert resolution.action
        assert resolution.execution_allowed is False


def test_red_team_challenge_is_not_override():
    assert "challenge_is_not_override" in AuthorityProtocol.invariant_rules()
    assert not AuthorityProtocol.can("RED_TEAM", AgentPower.RECOMMEND)


def test_unknown_agent_fails_closed():
    with pytest.raises(ValueError, match="Unknown authority profile"):
        AuthorityProtocol.profile("UNKNOWN_AGENT")
