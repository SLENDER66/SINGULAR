"""What a store transition is must not be decided by import order.

durable_recovery implements one transition outside durable.py and attaches it at
import time. It used to skip silently if anything was already bound under that
name -- and what it installs governs RECOVERY_REQUIRED -> COMPLETED, the
transition that turns an ambiguous external effect into a durable success.

Approval integrity used to arrive the same way, from a durable_approval module
that replaced weaker implementations left live in DurableStore. Deleting one
"unused" import in __init__.py would have reverted approvals to INSERT OR
REPLACE with no transition guard. Those methods now live in the class itself,
so there is nothing to revert to.
"""
import pytest

from singular.autopilot import ApprovalRequest, ApprovalStatus, Autonomy, DelegationContract
from singular.durable import DurableStore, install_store_extension
from singular.durable_recovery import confirm_execution_recovery_from_effect


def test_the_strict_recovery_transition_is_the_installed_one():
    assert DurableStore.confirm_execution_recovery_from_effect is confirm_execution_recovery_from_effect


def test_reinstalling_the_same_function_is_a_no_op():
    """Re-import must not raise: a module can be loaded more than once."""
    install_store_extension("confirm_execution_recovery_from_effect", confirm_execution_recovery_from_effect)

    assert DurableStore.confirm_execution_recovery_from_effect is confirm_execution_recovery_from_effect


def test_a_foreign_definition_is_refused_rather_than_silently_ignored():
    def weaker_confirm(self, execution_key, provider_idempotency_key):  # pragma: no cover - never installed
        raise AssertionError("this must never be reachable")

    weaker_confirm.__module__ = "somewhere.else"

    with pytest.raises(RuntimeError, match="refusing to install a second definition"):
        install_store_extension("confirm_execution_recovery_from_effect", weaker_confirm)

    assert DurableStore.confirm_execution_recovery_from_effect is confirm_execution_recovery_from_effect


def test_nothing_may_replace_a_method_the_store_defines_itself():
    def other_save(self, approval, mission_id=None):  # pragma: no cover - never installed
        raise AssertionError("this must never be reachable")

    other_save.__module__ = "somewhere.else"

    with pytest.raises(RuntimeError, match="refusing to install a second definition"):
        install_store_extension("save_approval", other_save)


def test_approval_identity_is_immutable_without_any_import_beyond_the_store(tmp_path):
    """The guarantee has to hold for whoever holds a DurableStore, not for whoever imported well."""
    store = DurableStore(tmp_path / "approvals.db")
    store.save_mission(DelegationContract("MIS-A", "objective", "expected", autonomy=Autonomy.PREPARE))
    approval = ApprovalRequest("ACT-1", "because", id="APP-1")
    store.save_approval(approval, "MIS-A")

    with pytest.raises(ValueError, match="immuable"):
        store.save_approval(ApprovalRequest("ACT-OTHER", "because", id="APP-1"), "MIS-A")

    store.update_approval("APP-1", ApprovalStatus.REJECTED)
    with pytest.raises(ValueError, match="Transition d'approbation interdite"):
        store.update_approval("APP-1", ApprovalStatus.APPROVED)
