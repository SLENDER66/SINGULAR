from singular.autopilot import ActionRequest, DelegationContract, Autonomy
from singular.audit import AuditTrail
from singular.config import Settings
from singular.health import check_system
from singular.models import WorldModel
from singular.production_runtime import AgentsSDKRuntime
from singular.security import ActionPolicy, ActionTier


def test_settings_are_safe_by_default(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SINGULAR_ENV", raising=False)
    settings = Settings.from_env()
    assert settings.openai_api_key is None
    assert settings.environment == "development"


def test_sensitive_action_is_black_and_requires_human():
    action = ActionRequest("wire_money", "transfer", 8, 1, 10)
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.BLACK
    assert decision.allowed is False
    assert decision.requires_human is True


def test_low_risk_reversible_action_is_green():
    action = ActionRequest("draft_summary", "prepare", 3, 1, 9)
    decision = ActionPolicy.evaluate(action)
    assert decision.tier == ActionTier.GREEN
    assert decision.allowed is True
    assert decision.requires_human is False


def test_audit_trail_is_append_only_from_public_api():
    trail = AuditTrail()
    event = trail.record("test", "unit", "ok", {"x": 1})
    assert trail.events() == (event,)
    assert trail.export()[0]["event_type"] == "test"


def test_health_is_ready_for_valid_core():
    from singular.autopilot import ExecutionBus
    status = check_system(WorldModel(), ExecutionBus())
    assert status.healthy is True
    assert status.ready is True
    assert all(status.checks.values())


def test_agents_sdk_boundary_does_not_require_key_to_import():
    runtime = AgentsSDKRuntime(Settings())
    assert runtime.status.model == "gpt-5.6"
    assert runtime.status.configured is False


def test_governor_contract_cannot_override_sensitive_flag():
    from singular.autopilot import Governor
    action = ActionRequest("anything", "sensitive", 5, 1, 10, sensitive=True)
    contract = DelegationContract("MIS-1", "obj", "result", autonomy=Autonomy.EXECUTE_AUTHORIZED)
    decision = Governor.evaluate(action, contract)
    assert decision.mode.value == "ESCALATE"


def test_v3_prepare_action_uses_supplied_contract():
    from singular.v3_operating_system import CandidateAction, SingularV3
    system = SingularV3()
    contract = DelegationContract(
        mission_id="MIS-42",
        objective="Test",
        expected_result="Prepared",
        autonomy=Autonomy.PREPARE,
    )
    decision = system.prepare_action(CandidateAction("draft_summary", 3, 2, 4, 1, 1, 9), contract=contract)
    assert decision.mode == Autonomy.PREPARE
    assert system.audit.events()[-1].event_type == "action_routing"
