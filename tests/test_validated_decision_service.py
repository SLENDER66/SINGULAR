import pytest

from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.mission_runtime import DurableMissionRuntime
from singular.validated_decision_service import ValidatedDecisionService, VerificationFailed
from tests.test_validated_pipeline import AUTHORIZED_HANDLER_CAPABILITY, _inputs, authorized_handler


def _verifier(action, execution):
    return execution.result == {"action_id": action.id, "executed": True}


def _service(tmp_path, verifier=_verifier):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "service.db"))
    service = ValidatedDecisionService(
        DurableExecutionEngine(runtime),
        issuer="service-test",
        verifier=verifier,
    )
    return runtime, service


def _kwargs(decision_id="DEC-SVC", execution_target=AUTHORIZED_HANDLER_CAPABILITY):
    contract, action, state, intervention, profile, dimensions = _inputs()
    return dict(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,),
        interventions=(intervention,),
        trajectory_profile=profile,
        trajectory_dimensions=dimensions,
        contract=contract,
        execution_target=execution_target,
        decision_id=decision_id,
        capacity_budget=2,
    )


def test_service_requires_trusted_verifier_at_composition(tmp_path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "service.db"))
    with pytest.raises(TypeError, match="trusted verifier"):
        ValidatedDecisionService(DurableExecutionEngine(runtime), issuer="service-test")


def test_service_build_and_execute_is_attested_first(tmp_path):
    runtime, service = _service(tmp_path)
    decision, attestation = service.build_and_attest(**_kwargs())
    runtime.store.save_mission(decision.contract)
    assert attestation.decision_id == decision.decision_id
    assert service.is_attested(decision)
    result = service.execute(decision, decision.global_report.action_id, authorized_handler)
    assert result.status == "COMPLETED"


def test_service_execute_verified_uses_only_composed_verifier(tmp_path):
    runtime, service = _service(tmp_path)
    decision, _ = service.build_and_attest(**_kwargs("DEC-SVC-VERIFY"))
    runtime.store.save_mission(decision.contract)
    result = service.execute_verified(decision, decision.global_report.action_id, authorized_handler)
    assert result.status == "COMPLETED"
    events = runtime.audit.events()
    assert any(event.event_type == "verification" and event.outcome == "VERIFIED" for event in events)


def test_service_execute_verified_cannot_accept_per_call_verifier(tmp_path):
    runtime, service = _service(tmp_path)
    decision, _ = service.build_and_attest(**_kwargs("DEC-SVC-VERIFY-INJECT"))
    runtime.store.save_mission(decision.contract)
    with pytest.raises(TypeError):
        service.execute_verified(
            decision,
            decision.global_report.action_id,
            authorized_handler,
            lambda *_: True,
        )


def test_service_execute_verified_fails_closed_and_audits_rejection(tmp_path):
    runtime, service = _service(tmp_path, verifier=lambda *_: False)
    decision, _ = service.build_and_attest(**_kwargs("DEC-SVC-VERIFY-FAIL"))
    runtime.store.save_mission(decision.contract)
    with pytest.raises(VerificationFailed):
        service.execute_verified(decision, decision.global_report.action_id, authorized_handler)
    events = runtime.audit.events()
    assert any(event.event_type == "verification" and event.outcome == "FAILED" for event in events)


def test_service_execute_verified_sanitizes_verifier_exception(tmp_path):
    def exploding_verifier(_action, _execution):
        raise RuntimeError("secret verifier detail")

    runtime, service = _service(tmp_path, verifier=exploding_verifier)
    decision, _ = service.build_and_attest(**_kwargs("DEC-SVC-VERIFY-EXC"))
    runtime.store.save_mission(decision.contract)

    with pytest.raises(VerificationFailed, match="verification failed") as exc_info:
        service.execute_verified(decision, decision.global_report.action_id, authorized_handler)
    assert "secret verifier detail" not in str(exc_info.value)
    assert any(event.event_type == "verification" and event.outcome == "FAILED" for event in runtime.audit.events())


def test_service_execute_verified_rejects_failed_execution_even_if_verifier_returns_true(tmp_path):
    runtime, service = _service(tmp_path)

    def failing_handler(_action):
        raise RuntimeError("handler failure")

    failing_capability = register_execution_capability(failing_handler, "cap_test_service_failing_handler")
    decision, _ = service.build_and_attest(**_kwargs("DEC-SVC-VERIFY-EXEC-FAIL", failing_capability))
    runtime.store.save_mission(decision.contract)
    with pytest.raises(VerificationFailed):
        service.execute_verified(decision, decision.global_report.action_id, failing_handler)
    event = [e for e in runtime.audit.events() if e.event_type == "verification"][-1]
    assert event.outcome == "FAILED"
    assert event.payload["reason"] == "execution_not_completed"


def test_service_revoke_closes_execution_without_mutating_decision(tmp_path):
    runtime, service = _service(tmp_path)
    decision, _ = service.build_and_attest(**_kwargs("DEC-SVC-REVOKE"))
    runtime.store.save_mission(decision.contract)
    service.revoke(decision.decision_id)
    assert service.is_attested(decision) is False
    with pytest.raises(PermissionError, match="attestée"):
        service.execute(decision, decision.global_report.action_id, authorized_handler)


def test_service_is_canonical_lifecycle_surface(tmp_path):
    runtime, service = _service(tmp_path)
    decision = service.build(**_kwargs("DEC-SVC-BUILD"))
    runtime.store.save_mission(decision.contract)
    assert service.is_attested(decision) is False
    with pytest.raises(PermissionError, match="attestée"):
        service.execute(decision, decision.global_report.action_id, authorized_handler)
