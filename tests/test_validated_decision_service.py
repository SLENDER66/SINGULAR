import pytest

from singular.validated_decision_service import ValidatedDecisionService
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from tests.test_validated_pipeline import AUTHORIZED_HANDLER_CAPABILITY, _inputs, authorized_handler


def _service(tmp_path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "service.db"))
    service = ValidatedDecisionService(DurableExecutionEngine(runtime), issuer="service-test")
    return runtime, service


def _kwargs(decision_id="DEC-SVC"):
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
        execution_target=AUTHORIZED_HANDLER_CAPABILITY,
        decision_id=decision_id,
        capacity_budget=2,
    )


def test_service_build_and_execute_is_attested_first(tmp_path):
    runtime, service = _service(tmp_path)
    decision, attestation = service.build_and_attest(**_kwargs())
    runtime.store.save_mission(decision.contract)

    assert attestation.decision_id == decision.decision_id
    assert service.is_attested(decision)
    result = service.execute(decision, decision.global_report.action_id, authorized_handler)
    assert result.status == "COMPLETED"


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
