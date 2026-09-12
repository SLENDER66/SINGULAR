import pytest

from singular.decision_attestation import DecisionAttestationStore, ValidatedDecisionIssuer
from singular.execution import ExecutionResult
from singular.validated_execution import ValidatedExecutionBoundary
from tests.test_validated_pipeline import AUTHORIZED_PROVIDER, _build_effect_decision


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


class ImpostorProvider:
    """Same shape and, previously, the same name as the authorized provider.

    The two positive tests below instantiated this local class while the decision
    authorizes tests.test_validated_pipeline:AuthorizedProvider, so the boundary
    refused them for provider substitution -- correctly, and for a reason those
    tests are not about. Renamed so the substitution case is visible rather than
    accidental.
    """

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
    provider = AUTHORIZED_PROVIDER
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
            AUTHORIZED_PROVIDER,
            provider_name="bounded-provider",
            operation="apply",
            payload=payload,
        )
    assert executor.calls == []


def test_external_effect_reconciliation_has_same_boundary():
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    provider = AUTHORIZED_PROVIDER
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
            AUTHORIZED_PROVIDER,
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
            AUTHORIZED_PROVIDER,
            provider_name="bounded-provider",
            operation="delete",
            payload=payload,
        )
    assert executor.calls == []


def test_external_effect_rejects_provider_substitution(tmp_path):
    """A provider of the same shape is not the provider the decision authorized."""
    decision, payload = _build_effect_decision()
    executor = FakeExecutor()
    boundary = _attested_boundary(decision, executor)

    with pytest.raises(PermissionError, match="fournisseur ne correspond pas"):
        boundary.execute_effect(
            decision,
            decision.global_report.action_id,
            ImpostorProvider(),
            provider_name="bounded-provider",
            operation="apply",
            payload=payload,
        )
    assert executor.calls == []
