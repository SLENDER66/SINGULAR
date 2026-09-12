from __future__ import annotations

from pathlib import Path

import pytest

from singular.autopilot import Autonomy
from singular.control_plane import SingularControlPlane
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.human_optimization import DomainState, Intervention
from singular.jarvis.llm import LLMResponse
from singular.jarvis.read_only import make_read_only_repository_tool, verify_read_only_result
from singular.jarvis.runtime import MissionProposal, ProposedAction
from singular.jarvis.validated_bridge import JarvisValidatedBridge
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.values import Vision


def _read_proposal():
    action = ProposedAction(
        name="read:README.md", description="Read one bounded repository file", impact=2, risk=0,
        reversibility=10, leverage=8, dependency=7, uncertainty=1, cost=1, learning=7,
        ownership=1, recurrence=1,
    )
    return MissionProposal(
        objective="Inspect repository state", expected_result="Bounded repository content is returned",
        context_needed=(), actions=(action,), llm=LLMResponse(text="{}", model="test"),
    )


def _read_inputs():
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("repository_read", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(
        Vision("Build a resilient long-term system"), money=1, time=1, capability=2, energy=1,
        freedom=1, ownership=1, learning=2, resilience=1, transmission=1,
    )
    return state, intervention, profile, {name: 0.8 for name in profile.weights}


def _build_read_decision(capability: str, control: SingularControlPlane, decision_id: str):
    state, intervention, profile, dimensions = _read_inputs()
    return JarvisValidatedBridge(control.runtime, control.decisions).build_and_attest(
        _read_proposal(), execution_target=capability, intervention_id=intervention.id,
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, capacity_budget=2, decision_id=decision_id,
        mission_kwargs={"autonomy": Autonomy.EXECUTE_REVERSIBLE},
    )


def test_jarvis_read_only_crosses_validated_boundary_and_requires_independent_verification(tmp_path: Path):
    (tmp_path / "README.md").write_text("SINGULAR", encoding="utf-8")
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    capability, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_jarvis_read_only_e2e")
    control = SingularControlPlane(
        runtime,
        verifier=lambda action, execution_result: verify_read_only_result(tmp_path, action, execution_result.result),
    )
    decision, attestation = _build_read_decision(capability, control, "DEC-JARVIS-READ-E2E")
    assert attestation.decision_id == decision.decision_id
    assert control.decisions.is_attested(decision)
    assert decision.verify()
    assert decision.contract.autonomy == Autonomy.EXECUTE_REVERSIBLE
    result = control.decisions.execute_verified(decision, decision.authorized_actions[0].id, handler)
    assert result.status == "COMPLETED"
    assert result.result["path"] == "README.md"
    audit_events = runtime.store.audit_events()
    verification_events = [event for event in audit_events if event.get("event_type") == "verification"]
    assert verification_events
    assert verification_events[-1]["outcome"] == "VERIFIED"
    assert verification_events[-1]["payload"]["decision_id"] == decision.decision_id
    assert verification_events[-1]["payload"]["action_id"] == decision.authorized_actions[0].id
    assert verification_events[-1]["payload"]["execution_key"] == result.execution_key
    assert "SINGULAR" not in str(verification_events[-1]["payload"])
    second = control.decisions.execute_verified(decision, decision.authorized_actions[0].id, handler)
    assert second.execution_key == result.execution_key


def test_jarvis_read_only_verification_rejects_file_changed_after_execution(tmp_path: Path):
    (tmp_path / "README.md").write_text("SINGULAR", encoding="utf-8")
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    capability, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_jarvis_read_only_changed_file")

    def tampering_verifier(action, execution_result):
        (tmp_path / "README.md").write_text("TAMPERED", encoding="utf-8")
        return verify_read_only_result(tmp_path, action, execution_result.result)

    control = SingularControlPlane(runtime, verifier=tampering_verifier)
    decision, _ = _build_read_decision(capability, control, "DEC-JARVIS-READ-CHANGED")
    with pytest.raises(PermissionError, match="verification"):
        control.decisions.execute_verified(decision, decision.authorized_actions[0].id, handler)
    audit_events = runtime.store.audit_events()
    assert any(event.get("event_type") == "verification" and event.get("outcome") == "FAILED" for event in audit_events)


def test_jarvis_read_only_rejects_handler_substitution_before_effect(tmp_path: Path):
    (tmp_path / "README.md").write_text("SINGULAR", encoding="utf-8")
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    control = SingularControlPlane(runtime)
    capability, _handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_jarvis_read_only_original")
    decision, _ = _build_read_decision(capability, control, "DEC-JARVIS-READ-SUB")
    _replacement_capability, replacement_handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_jarvis_read_only_replacement")
    with pytest.raises(PermissionError, match="capability"):
        control.decisions.execute_verified(decision, decision.authorized_actions[0].id, replacement_handler)
    execution_key = runtime.store.idempotency_key("execute", decision.contract.mission_id, decision.authorized_actions[0].id)
    assert not runtime.store.get_execution(execution_key)


def test_jarvis_read_only_revocation_blocks_execution(tmp_path: Path):
    (tmp_path / "README.md").write_text("SINGULAR", encoding="utf-8")
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    control = SingularControlPlane(runtime)
    capability, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_jarvis_read_only_revoke")
    decision, _ = _build_read_decision(capability, control, "DEC-JARVIS-READ-REVOKE")
    control.decisions.revoke(decision.decision_id)
    with pytest.raises(PermissionError, match="attestée"):
        control.decisions.execute_verified(decision, decision.authorized_actions[0].id, handler)
    execution_key = runtime.store.idempotency_key("execute", decision.contract.mission_id, decision.authorized_actions[0].id)
    assert not runtime.store.get_execution(execution_key)
