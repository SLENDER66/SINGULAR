from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.v32_governed_core import GovernedMission, Specialist, WorkforceRouter


def test_workforce_router_selects_relevant_specialists():
    plan = WorkforceRouter().plan("MIS-1", "Améliorer mes revenus et trouver un emploi")
    assert Specialist.STRATEGY in plan.specialists
    assert Specialist.FINANCE in plan.specialists
    assert Specialist.CAREER in plan.specialists


def test_red_team_blocks_high_risk_without_contract():
    result = GovernedMission().route(ActionRequest("publish_sensitive", "x", 9, 9, 1, sensitive=True))
    assert result.allowed is False
    assert result.governor.mode == Autonomy.BLOCK


def test_governed_mission_prepares_without_execution_authority():
    contract = DelegationContract("MIS-2", "améliorer les compétences", "plan", autonomy=Autonomy.PREPARE)
    action = ActionRequest("research_options", "x", 3, 2, 8)
    result = GovernedMission().route(action, contract)
    assert result.allowed is True
    assert result.governor.mode == Autonomy.PREPARE


def test_forbidden_contract_action_is_blocked():
    contract = DelegationContract("MIS-3", "test", "test", autonomy=Autonomy.EXECUTE_REVERSIBLE, forbidden_actions=("delete_account",))
    action = ActionRequest("delete_account", "x", 2, 1, 9)
    result = GovernedMission().route(action, contract)
    assert result.allowed is False
    assert result.governor.mode == Autonomy.BLOCK
