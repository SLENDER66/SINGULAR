"""Grafting a transition onto DurableStore must not be decided by import order.

Two modules implement store transitions outside durable.py and attach them at
import time. They disagreed about conflicts: the recovery module skipped
silently if anything was already bound, the approval module overwrote unless the
binding was already its own. The graft the recovery module installs governs
RECOVERY_REQUIRED -> COMPLETED -- the transition that turns an ambiguous
external effect into a durable success -- so a weaker definition winning by
import order is the fail-open shape the boundary exists to prevent.
"""
import pytest

from singular.durable import DurableStore, install_store_extension
from singular.durable_approval import save_approval, update_approval
from singular.durable_recovery import confirm_execution_recovery_from_effect


def test_the_strict_definitions_are_the_installed_ones():
    assert DurableStore.confirm_execution_recovery_from_effect is confirm_execution_recovery_from_effect
    assert DurableStore.save_approval is save_approval
    assert DurableStore.update_approval is update_approval


def test_reinstalling_the_same_function_is_a_no_op():
    """Re-import must not raise: a module can be loaded more than once."""
    install_store_extension("confirm_execution_recovery_from_effect", confirm_execution_recovery_from_effect)
    install_store_extension("save_approval", save_approval, replaces_base=True)

    assert DurableStore.confirm_execution_recovery_from_effect is confirm_execution_recovery_from_effect


def test_a_foreign_definition_is_refused_rather_than_silently_ignored():
    def weaker_confirm(self, execution_key, provider_idempotency_key):  # pragma: no cover - never installed
        raise AssertionError("this must never be reachable")

    weaker_confirm.__module__ = "somewhere.else"

    with pytest.raises(RuntimeError, match="refusing to install a second definition"):
        install_store_extension("confirm_execution_recovery_from_effect", weaker_confirm)

    assert DurableStore.confirm_execution_recovery_from_effect is confirm_execution_recovery_from_effect


def test_replacing_the_base_definition_stays_deliberate():
    """durable.py's own version may be replaced only when the caller says so."""

    def other_save(self, approval, mission_id=None):  # pragma: no cover - never installed
        raise AssertionError("this must never be reachable")

    other_save.__module__ = "somewhere.else"

    with pytest.raises(RuntimeError, match="refusing to install a second definition"):
        install_store_extension("save_approval", other_save, replaces_base=True)

    assert DurableStore.save_approval is save_approval
