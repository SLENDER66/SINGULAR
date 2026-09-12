import pytest

from singular.autopilot import ApprovalRequest, ApprovalStatus, DelegationContract
from singular.durable import DurableStore


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(DelegationContract(mission_id="MIS-APP", objective="test", expected_result="done"))
    return store


def test_existing_approval_cannot_be_replaced(tmp_path):
    store = _store(tmp_path)
    original = ApprovalRequest("ACT-1", "approved for execution", ApprovalStatus.PENDING, "APR-1")
    store.save_approval(original, "MIS-APP")

    with pytest.raises(ValueError, match="approbation existante est immuable"):
        store.save_approval(ApprovalRequest("ACT-2", "different", ApprovalStatus.PENDING, "APR-1"), "MIS-OTHER")

    persisted = store.get_approval("APR-1")
    assert persisted.action_id == "ACT-1"
    assert persisted.status is ApprovalStatus.PENDING


def test_terminal_approval_cannot_be_rewritten(tmp_path):
    store = _store(tmp_path)
    store.save_approval(ApprovalRequest("ACT-1", "approved", ApprovalStatus.PENDING, "APR-1"), "MIS-APP")
    store.update_approval("APR-1", ApprovalStatus.APPROVED)

    with pytest.raises(ValueError, match="Transition d'approbation interdite"):
        store.update_approval("APR-1", ApprovalStatus.REJECTED)

    assert store.get_approval("APR-1").status is ApprovalStatus.APPROVED


def test_same_terminal_approval_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.save_approval(ApprovalRequest("ACT-1", "approved", ApprovalStatus.PENDING, "APR-1"), "MIS-APP")
    store.update_approval("APR-1", ApprovalStatus.APPROVED)

    result = store.update_approval("APR-1", ApprovalStatus.APPROVED)

    assert result.status is ApprovalStatus.APPROVED
