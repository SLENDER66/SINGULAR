"""A capability token must keep meaning the same artifact across a restart.

ExecutionCapabilityRegistry maps tokens to live objects, so it is empty in a
fresh process. The decision naming a token and the attestation authorizing it
are durable, so before this the pair

    old capability token  +  freshly registered arbitrary object

was a valid authorization: the token said nothing about which code it stood for.
"""
from pathlib import Path

import pytest

from singular.decision_attestation import ValidatedDecisionIssuer
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.execution_capability import (
    RUNTIME_VERSION,
    DurableCapabilityStore,
    ExecutionCapabilityRegistry,
    artifact_fingerprint,
)
from singular.mission_runtime import DurableMissionRuntime
from tests.support import SUPPORT_HANDLER_CAPABILITY, build_decision, support_handler


def authorized(action):
    return {"action_id": action.id, "executed": True}


def impostor(action):
    return {"action_id": action.id, "executed": "by an impostor"}


# --- artifact fingerprints ---------------------------------------------------

def test_fingerprint_distinguishes_two_implementations():
    assert artifact_fingerprint(authorized) != artifact_fingerprint(impostor)


def test_fingerprint_is_stable_for_the_same_implementation():
    assert artifact_fingerprint(authorized) == artifact_fingerprint(authorized)


def test_fingerprint_covers_provider_objects_by_their_class():
    class Provider:
        def execute(self, request, key):
            return "a"

    class OtherProvider:
        def execute(self, request, key):
            return "b"

    assert artifact_fingerprint(Provider()) == artifact_fingerprint(Provider())
    assert artifact_fingerprint(Provider()) != artifact_fingerprint(OtherProvider())


def test_fingerprint_names_the_runtime_it_was_compiled_for():
    record = DurableCapabilityStore(":memory:").bind("cap_runtime", authorized)
    assert record.runtime_version == RUNTIME_VERSION


# --- the restart bypass ------------------------------------------------------

def test_old_token_plus_new_object_is_refused_after_restart(tmp_path: Path):
    """The scenario this whole module exists for."""
    path = tmp_path / "capabilities.db"
    DurableCapabilityStore(path).bind("cap_restart", authorized)

    restarted = DurableCapabilityStore(path)
    assert restarted.verify("cap_restart", authorized) is True
    assert restarted.verify("cap_restart", impostor) is False
    with pytest.raises(PermissionError, match="different executable artifact"):
        restarted.bind("cap_restart", impostor)


def test_in_memory_registry_alone_still_accepts_an_impostor_after_restart():
    """Why the durable half is needed: the memory half cannot see the past."""
    first = ExecutionCapabilityRegistry()
    token = first.register(authorized, "cap_memory_only")

    restarted = ExecutionCapabilityRegistry()
    assert restarted.matches(token, impostor) is False  # nothing registered yet
    assert restarted.register(impostor, token) == token
    assert restarted.matches(token, impostor) is True


def test_a_registry_with_a_durable_store_refuses_that_impostor(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    first = ExecutionCapabilityRegistry(DurableCapabilityStore(path))
    token = first.register(authorized, "cap_durable")

    restarted = ExecutionCapabilityRegistry(DurableCapabilityStore(path))
    with pytest.raises(PermissionError, match="different executable artifact"):
        restarted.register(impostor, token)
    assert restarted.register(authorized, token) == token
    assert restarted.matches(token, authorized) is True


# --- revocation and rotation -------------------------------------------------

def test_revocation_survives_restart_and_cannot_be_undone(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    store.bind("cap_revoked", authorized)
    store.revoke("cap_revoked")

    restarted = DurableCapabilityStore(path)
    assert restarted.verify("cap_revoked", authorized) is False
    with pytest.raises(PermissionError, match="revoked capability id cannot be re-registered"):
        restarted.bind("cap_revoked", authorized)


def test_revoking_twice_is_refused_rather_than_silently_accepted(tmp_path: Path):
    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    store.bind("cap_twice", authorized)
    store.revoke("cap_twice")
    with pytest.raises(KeyError):
        store.revoke("cap_twice")


def test_rotation_issues_a_new_token_rather_than_reviving_one(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    registry = ExecutionCapabilityRegistry(DurableCapabilityStore(path))
    old = registry.register(authorized, "cap_rotate_old")
    registry.revoke(old)
    new = registry.register(authorized, "cap_rotate_new")
    assert new != old
    assert registry.matches(new, authorized) is True
    assert registry.matches(old, authorized) is False


# --- the execution boundary --------------------------------------------------

def _engine(tmp_path: Path, decision):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    engine = DurableExecutionEngine(runtime)
    ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
    return engine


def test_execution_records_what_the_token_meant(tmp_path: Path):
    decision = build_decision(decision_id="DEC-CAP-REC", mission_id="MIS-CAP-REC")
    engine = _engine(tmp_path, decision)
    engine.execute_validated(decision, support_handler)

    record = engine.capability_store.get(SUPPORT_HANDLER_CAPABILITY)
    assert record is not None
    assert record.artifact_fingerprint == artifact_fingerprint(support_handler)
    assert record.active is True


def test_execution_refuses_a_capability_revoked_between_validation_and_the_call(tmp_path: Path):
    """The validate -> lookup -> revoke -> execute race, closed at the last moment."""
    decision = build_decision(decision_id="DEC-CAP-RACE", mission_id="MIS-CAP-RACE")
    engine = _engine(tmp_path, decision)
    engine.capability_store.bind(SUPPORT_HANDLER_CAPABILITY, support_handler)
    engine.capability_store.revoke(SUPPORT_HANDLER_CAPABILITY)

    with pytest.raises(PermissionError):
        engine.execute_validated(decision, support_handler)


def test_capability_schema_version_mismatch_is_refused(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    with store._connect() as conn:
        conn.execute("UPDATE execution_capability_schema SET version=99")
    with pytest.raises(RuntimeError, match="does not match"):
        DurableCapabilityStore(path)
