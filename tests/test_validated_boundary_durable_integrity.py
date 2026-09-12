"""What durable incoherence the boundary refuses to execute over, and what it does not.

The boundary refuses every execution while the integrity scan is dirty, and
nothing here repairs a row. Scanned over the whole database, that meant one bad
row anywhere -- an unrelated mission, a write outside the API, a corrupt page --
shut every mission for ever, with no supported way back. The scan is scoped to
the mission being executed: the refusal still lands exactly where the executor
is about to read, and a bad row costs the mission it belongs to rather than the
system.
"""
import sqlite3

import pytest

from singular.decision_attestation import DecisionAttestationStore
from singular.durable import DurableStore
from singular.durable_integrity import DurableIntegrityChecker
from singular.effects import ExternalEffectCoordinator
from singular.validated_execution import ValidatedExecutionBoundary
from tests.test_validated_trajectory_decision import build


class FakeExecutor:
    def __init__(self, store):
        self.store = store

    def execute_validated(self, decision, handler):
        raise AssertionError("execution must be rejected before reaching the executor")


def _boundary(tmp_path, decision):
    durable = DurableStore(tmp_path / "durable.db")
    ExternalEffectCoordinator(durable)
    attestation_store = DecisionAttestationStore(tmp_path / "attestations.db")
    attestation_store.issue(decision)
    return durable, ValidatedExecutionBoundary(FakeExecutor(durable), attestation_store)


def _orphan_effect(durable: DurableStore) -> None:
    """An external effect naming an execution that does not exist."""
    with sqlite3.connect(durable.path) as conn:
        conn.execute(
            "INSERT INTO external_effects "
            "(provider_idempotency_key,execution_key,provider,operation,payload_fingerprint,action_fingerprint,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("orphan", "missing-execution", "provider", "write", "payload", "action", "INTENT", "now", "now"),
        )


def test_the_boundary_refuses_when_this_mission_is_incoherent(tmp_path):
    """Fail-closed where it counts: the state this execution is about to read."""
    decision = build()
    durable, boundary = _boundary(tmp_path, decision)
    durable.save_mission(decision.contract)
    with durable._connect() as conn:
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,'')",
            ("exec-broken", decision.contract.mission_id, decision.global_report.action_id, "RUNNING"),
        )

    with pytest.raises(RuntimeError, match="Durable state integrity failure"):
        boundary.execute(decision, decision.global_report.action_id, lambda action: True)


def test_the_refusal_names_the_mission_it_is_about(tmp_path):
    decision = build()
    durable, boundary = _boundary(tmp_path, decision)
    durable.save_mission(decision.contract)
    with durable._connect() as conn:
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,'')",
            ("exec-broken", decision.contract.mission_id, decision.global_report.action_id, "RUNNING"),
        )

    with pytest.raises(RuntimeError, match=f"mission {decision.contract.mission_id}"):
        boundary.execute(decision, decision.global_report.action_id, lambda action: True)


def test_a_bad_row_outside_this_mission_no_longer_stops_it_for_ever(tmp_path):
    """The trade, stated: bounded blast radius instead of a permanent outage.

    An orphan effect belongs to no mission -- its execution is what is missing --
    so nothing this mission is about to read is incoherent. Refusing here shut
    every mission in the system, permanently, with no operation that repairs it.
    """
    decision = build()
    durable, boundary = _boundary(tmp_path, decision)
    durable.save_mission(decision.contract)
    _orphan_effect(durable)

    with pytest.raises(AssertionError, match="rejected before reaching the executor"):
        boundary.execute(decision, decision.global_report.action_id, lambda action: True)


def test_the_whole_database_scan_still_reports_that_row(tmp_path):
    """The other half of the trade: the canary is still there, for the operator."""
    decision = build()
    durable, _ = _boundary(tmp_path, decision)
    durable.save_mission(decision.contract)
    _orphan_effect(durable)

    report = DurableIntegrityChecker(durable).check()
    assert any(item.rule == "EFFECT-EXECUTION" for item in report.violations)
    assert DurableIntegrityChecker(durable).check(decision.contract.mission_id).clean
