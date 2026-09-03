import sqlite3

import pytest

from singular.durable import DurableStore
from singular.effects import ExternalEffectCoordinator
from singular.validated_execution import ValidatedExecutionBoundary
from test_validated_trajectory_decision import build


class FakeExecutor:
    def __init__(self, store):
        self.store = store

    def execute_validated(self, decision, handler):
        raise AssertionError("execution must be rejected before reaching the executor")


def test_validated_boundary_fails_closed_on_corrupted_durable_state(tmp_path):
    durable = DurableStore(tmp_path / "durable.db")
    ExternalEffectCoordinator(durable)
    with sqlite3.connect(durable.path) as conn:
        conn.execute(
            "INSERT INTO external_effects "
            "(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("orphan", "missing-execution", "provider", "write", "payload", "INTENT", "now", "now"),
        )

    executor = FakeExecutor(durable)
    attestation = tmp_path / "attestations.db"
    from singular.decision_attestation import DecisionAttestationStore
    attestation_store = DecisionAttestationStore(attestation)
    decision = build()
    attestation_store.issue(decision)
    boundary = ValidatedExecutionBoundary(executor, attestation_store)

    with pytest.raises(RuntimeError, match="Durable state integrity failure"):
        boundary.execute(decision, decision.global_report.action_id, lambda action: True)
