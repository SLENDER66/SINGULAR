from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime


def _setup(tmp_path: Path, *, autonomy: Autonomy = Autonomy.EXECUTE_REVERSIBLE):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "s.db"))
    contract = runtime.create_mission("external effect", "provider operation completed", autonomy=autonomy)
    engine = DurableExecutionEngine(runtime)
    return runtime, contract, engine


def test_raw_external_effect_api_is_disabled(tmp_path: Path):
    runtime, contract, engine = _setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.execute_effect(action, contract.mission_id, object(), provider_name="fake", operation="send", payload={"to": "a"})

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED


def test_raw_effect_reconciliation_api_is_disabled(tmp_path: Path):
    runtime, contract, engine = _setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)

    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.reconcile_effect(action, contract.mission_id, object(), provider_name="fake", operation="send", payload={"to": "a"})

    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED


def test_sensitive_raw_effect_never_reaches_provider(tmp_path: Path):
    runtime, contract, engine = _setup(tmp_path, autonomy=Autonomy.PREPARE)
    action = ActionRequest("send_application", "send", 5, 6, 6)

    class Provider:
        calls = 0

        def execute(self, request, idempotency_key):
            self.calls += 1
            raise AssertionError("provider must not be reached")

    provider = Provider()
    with pytest.raises(PermissionError, match="ValidatedTrajectoryDecision"):
        engine.execute_effect(action, contract.mission_id, provider, provider_name="fake", operation="send", payload={"to": "a"})
    assert provider.calls == 0
    assert runtime.state(contract.mission_id).status == MissionStatus.CREATED


def test_cached_governance_route_still_detects_drift(tmp_path: Path):
    runtime, contract, engine = _setup(tmp_path)
    action = ActionRequest("safe_action", "send", 1, 1, 10)

    first = runtime.route(action, contract.mission_id)
    assert first.can_execute is True

    contract_data = runtime.store.load_mission(contract.mission_id)
    assert contract_data is not None
    updated = contract_data.__class__(
        mission_id=contract_data.mission_id,
        objective=contract_data.objective,
        expected_result=contract_data.expected_result,
        autonomy=Autonomy.PREPARE,
        budget_limit=contract_data.budget_limit,
        deadline=contract_data.deadline,
        forbidden_actions=contract_data.forbidden_actions,
        escalation_conditions=contract_data.escalation_conditions,
        success_criteria=contract_data.success_criteria,
    )
    runtime.store.save_mission(updated)

    with pytest.raises(PermissionError, match="gouvernance a changé"):
        runtime.route(action, contract.mission_id)
