import pytest

from singular.autopilot import ApprovalRequest, ApprovalStatus, DelegationContract
from singular.durable import DurableStore


def _store(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(
        DelegationContract(
            mission_id="MIS-APPROVAL",
            objective="test",
            expected_result="done",
        )
    )
    return store


def test_approval_identity_cannot_be_replaced(tmp_path):
    store = _store(tmp_path)
    approval = ApprovalRequest("ACT-1", "human review")
    store.save_approval(approval, "MIS-APPROVAL")

    with pytest.raises(ValueError, match="identité.*immuable"):
        store.save_approval(ApprovalRequest("ACT-2", "different", id=approval.id), "MIS-APPROVAL")

    persisted = store.get_approval(approval.id)
    assert persisted.action_id == "ACT-1"
    assert persisted.reason == "human review"


def test_terminal_approval_cannot_be_rewritten(tmp_path):
    store = _store(tmp_path)
    approval = ApprovalRequest("ACT-1", "human review")
    store.save_approval(approval, "MIS-APPROVAL")
    store.update_approval(approval.id, ApprovalStatus.APPROVED)

    with pytest.raises(ValueError, match="Transition d'approbation interdite"):
        store.update_approval(approval.id, ApprovalStatus.REJECTED)

    assert store.get_approval(approval.id).status is ApprovalStatus.APPROVED


def test_concurrent_terminal_decision_is_fail_closed(tmp_path):
    store = _store(tmp_path)
    approval = ApprovalRequest("ACT-1", "human review")
    store.save_approval(approval, "MIS-APPROVAL")

    first = store.update_approval(approval.id, ApprovalStatus.REJECTED)
    second = store.update_approval(approval.id, ApprovalStatus.REJECTED)

    assert first.status is ApprovalStatus.REJECTED
    assert second.status is ApprovalStatus.REJECTED
