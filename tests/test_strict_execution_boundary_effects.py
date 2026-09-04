import pytest

from singular.decision_attestation import DecisionAttestationStore, ValidatedDecisionIssuer
from singular.execution import ExecutionResult
from singular.validated_execution import ValidatedExecutionBoundary
from tests.test_validated_pipeline import _build_effect_decision


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute_validated(self, decision, handler):
        self.calls.append(("handler", decision, handler))
        return ExecutionResult("E", decision.contract.mission_id, decision.global_report.action_id, "COMPLETED")

    def execute_effect_validated(self, decision, provider, *, provider_name, operation, payload):
        self.calls.append(("effect", decision, provider, provider_name, operation, payload))
        return ExecutionResult("E", decision.contract.mission_id, decision.global_report.action_id, "COMPLETED")

    def reconcile_effect_validated(self, decision, provider, *, provider_name, operation, payload):
        self.calls.append(("reconcile", decision, provider, provider_name, operation, payload))
        return ExecutionResult("E", decision.contract.mission_id, decision.global_report.action_id, "COMPLETED")


class AuthorizedProvider:
    def execute(self, request, idempotency_key):
        raise AssertionError("fake boundary must intercept")

    def reconcile(self, request, idempotency_key):
        raise AssertionError("fake boundary must intercept")



def _attested_boundary(decision, executor):
    store = DecisionAttestationStore(":memory:")
    ValidatedDecisionIssuer(store).issue(decision)
    return ValidatedExecutionBoundary(executor, store)


def test_external_effect_has_a_strict_boundary():
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    provider = AuthorizedProvider()
    boundary = _attested_boundary(decision, executor)

    result = boundary.execute_effect(
        decision,
        decision.global_report.action_id,
        provider,
        provider_name="bounded-provider",
        operation="apply",
        payload=payload,
    )

    assert result.status == "COMPLETED"
    assert executor.calls[0][0] == "effect"


def test_external_effect_cannot_bypass_attestation():
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    boundary = ValidatedExecutionBoundary(executor, DecisionAttestationStore(":memory:"))

    with pytest.raises(PermissionError, match="durablement attestée"):
        boundary.execute_effect(
            decision,
            decision.global_report.action_id,
            AuthorizedProvider(),
            provider_name="bounded-provider",
            operation="apply",
            payload=payload,
        )
    assert executor.calls == []


def test_external_effect_reconciliation_has_same_boundary():
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    provider = AuthorizedProvider()
    boundary = _attested_boundary(decision, executor)

    result = boundary.reconcile_effect(
        decision,
        decision.global_report.action_id,
        provider,
        provider_name="bounded-provider",
        operation="apply",
        payload=payload,
    )

    assert result.status == "COMPLETED"
    assert executor.calls[0][0] == "reconcile"


def test_external_effect_rejects_action_substitution():
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    boundary = _attested_boundary(decision, executor)

    with pytest.raises(PermissionError, match="action demandée"):
        boundary.execute_effect(
            decision,
            "UNKNOWN-ACTION",
            AuthorizedProvider(),
            provider_name="bounded-provider",
            operation="apply",
            payload=payload,
        )
    assert executor.calls == []


def test_external_effect_rejects_operation_substitution_before_executor():
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    boundary = _attested_boundary(decision, executor)

    with pytest.raises(PermissionError, match="fournisseur ou l'opération"):
        boundary.execute_effect(
            decision,
            decision.global_report.action_id,
            AuthorizedProvider(),
            provider_name="bounded-provider",
            operation="delete",
            payload=payload,
        )
    assert executor.calls == []
