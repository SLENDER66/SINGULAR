"""The durable audit chain must grow across successive operations.

DurableMissionRuntime._persist_new_audit_events re-sent the entire in-memory
trail on every call, so the second audited operation replayed event #1 and
DurableStore refused it as not inserting at the head of the chain. The ordinary
public sequence -- create_mission() then route() -- always raised, and the audit
trail could never hold more than one event. Existing tests missed it because
they seeded missions with store.save_mission(), which records nothing.
"""
from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy
from singular.durable import DurableStore
from singular.mission_runtime import DurableMissionRuntime


def _runtime(tmp_path: Path) -> DurableMissionRuntime:
    return DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))


def _escalating_action(label: str = "send") -> ActionRequest:
    return ActionRequest("send_application", label, 5, 6, 6)


def _approval_id(runtime: DurableMissionRuntime, mission_id: str, label: str = "send") -> str:
    """route() records its verdict; approvals add a second audited operation."""
    governed = runtime.route(_escalating_action(label), mission_id)
    assert governed.governor.approval_id
    return governed.governor.approval_id


def test_two_audited_operations_in_a_row_both_persist(tmp_path: Path):
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "application prepared", autonomy=Autonomy.PREPARE)
    runtime.approve(_approval_id(runtime, contract.mission_id))

    persisted = runtime.store.audit_events()
    assert len(persisted) >= 2
    assert [event["payload"]["audit_sequence"] for event in persisted] == list(range(1, len(persisted) + 1))
    assert runtime.store.verify_audit_integrity() is True


def test_repeated_persist_calls_are_idempotent(tmp_path: Path):
    runtime = _runtime(tmp_path)
    runtime.create_mission("career", "prepared", autonomy=Autonomy.PREPARE)
    before = len(runtime.store.audit_events())
    runtime._persist_new_audit_events()
    runtime._persist_new_audit_events()
    assert len(runtime.store.audit_events()) == before


def test_audit_chain_continues_after_restart(tmp_path: Path):
    first = _runtime(tmp_path)
    contract = first.create_mission("career", "prepared", autonomy=Autonomy.PREPARE)
    count = len(first.store.audit_events())

    restarted = _runtime(tmp_path)
    restarted.approve(_approval_id(restarted, contract.mission_id))

    persisted = restarted.store.audit_events()
    assert len(persisted) > count
    assert [event["payload"]["audit_sequence"] for event in persisted] == list(range(1, len(persisted) + 1))
    assert restarted.store.verify_audit_integrity() is True


def test_out_of_order_event_is_refused_rather_than_skipped(tmp_path: Path):
    """Persisting must fail loudly on a gap, never leave one behind quietly."""
    runtime = _runtime(tmp_path)
    runtime.create_mission("career", "prepared", autonomy=Autonomy.PREPARE)
    replayed = runtime.store.audit_events()[0]
    event = runtime.audit.events()[0]
    assert replayed["payload"]["audit_sequence"] == 1

    with pytest.raises(ValueError, match="tête de la chaîne"):
        runtime.store.record_audit(event)


def test_many_successive_operations_keep_one_unbroken_chain(tmp_path: Path):
    runtime = _runtime(tmp_path)
    contract = runtime.create_mission("career", "prepared", autonomy=Autonomy.PREPARE)
    runtime.approve(_approval_id(runtime, contract.mission_id, "send"))
    for index in range(4):
        other = runtime.create_mission(f"career {index}", "prepared", autonomy=Autonomy.PREPARE)
        runtime.approve(_approval_id(runtime, other.mission_id, f"send {index}"))

    persisted = runtime.store.audit_events()
    sequences = [event["payload"]["audit_sequence"] for event in persisted]
    assert sequences == list(range(1, len(persisted) + 1))
    assert len(persisted) == len(runtime.audit.events())
    assert runtime.store.verify_audit_integrity() is True
