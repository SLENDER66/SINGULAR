"""Guard the artifact binding a rehydrated decision would depend on.

UPDATE: when this file was written the decision bound no artifact at all, and
the only thing standing between an old capability token and an arbitrary object
after a restart was that no serializer existed. Both halves have since been
built -- the decision carries execution_artifact_fingerprint, and
DurableCapabilityStore records what a token durably means -- so these tests have
changed role: they now hold that binding in place. If the artifact field is ever
dropped while a serializer exists, they fail, which is the state the original
note below describes.

Original note:

ExecutionCapabilityRegistry is process-local: `cap_...` tokens map to in-memory
objects and nothing is persisted. A durable decision, by contrast, survives a
restart -- its `execution_target` is a plain string inside `context_fingerprint`,
and DecisionAttestationStore keeps the attestation in SQLite. So if a
ValidatedTrajectoryDecision could be rehydrated after a restart, the pair

    old capability token  +  freshly registered arbitrary object

would become a valid authorization, because register() succeeds for any object
once the in-memory registry is empty again.

Today that attack is blocked only because no serializer exists: a decision
cannot be reconstituted at all. That is an accident of incompleteness, not a
designed control, and it would disappear silently the moment someone adds a
`to_dict`/`from_dict` pair for convenience.

These tests fail if such a round trip appears without the decision also binding
a verifiable artifact identity. Do not delete them to make a serializer land --
bind the artifact first (capability/artifact/provider fingerprint, version,
epoch), then teach ARTIFACT_BINDING_FIELDS about it.
"""
import inspect

import pytest

from singular import validated_trajectory_decision as vtd
from singular.validated_trajectory_decision import ValidatedTrajectoryDecision

#: Names that would make a decision reconstructible from inert data.
DESERIALIZATION_NAMES = frozenset(
    {"from_dict", "from_json", "from_payload", "parse", "parse_raw", "loads", "deserialize", "restore", "rehydrate", "read"}
)
SERIALIZATION_NAMES = frozenset({"to_dict", "to_json", "dumps", "serialize", "as_dict", "json", "dump"})

#: Fields that would tie a rehydrated decision to the code it authorizes.
#: A durable `cap_...` string is an identifier, never a proof of artifact identity.
ARTIFACT_BINDING_FIELDS = frozenset(
    {
        "execution_artifact_fingerprint",
        "capability_fingerprint",
        "provider_fingerprint",
        "capability_epoch",
        "runtime_fingerprint",
    }
)


def _decision_field_names() -> set[str]:
    return set(ValidatedTrajectoryDecision.__dataclass_fields__)


def _public_methods(names: frozenset[str]) -> set[str]:
    found = set()
    for name, member in inspect.getmembers(ValidatedTrajectoryDecision):
        if name.startswith("__"):
            continue
        if name in names and (inspect.isfunction(member) or inspect.ismethod(member)):
            found.add(name)
    return found


def _binds_an_artifact() -> bool:
    return bool(_decision_field_names() & ARTIFACT_BINDING_FIELDS)


def test_decision_cannot_be_rehydrated_without_binding_an_artifact():
    """A restart must not turn an old token plus a new object into authorization."""
    entry_points = _public_methods(DESERIALIZATION_NAMES)
    if entry_points and not _binds_an_artifact():
        pytest.fail(
            "ValidatedTrajectoryDecision gained deserialization entry points "
            f"{sorted(entry_points)} while binding no artifact identity. "
            f"Add one of {sorted(ARTIFACT_BINDING_FIELDS)} to the decision and to its "
            "fingerprinted payload before a decision can be reconstructed from data."
        )


def test_decision_serialization_requires_artifact_binding_too():
    """A dump is half a round trip; it is where a persisted decision starts."""
    entry_points = _public_methods(SERIALIZATION_NAMES)
    if entry_points and not _binds_an_artifact():
        pytest.fail(
            "ValidatedTrajectoryDecision gained serialization entry points "
            f"{sorted(entry_points)} while binding no artifact identity. "
            "Persisting a decision whose only execution binding is a process-local "
            "cap_ token reopens the restart bypass."
        )


def test_module_exposes_no_decision_decoder():
    """The escape hatch is a module-level helper rather than a method."""
    decoders = {
        name
        for name, member in inspect.getmembers(vtd, inspect.isfunction)
        if not name.startswith("_") and name in DESERIALIZATION_NAMES
    }
    if decoders and not _binds_an_artifact():
        pytest.fail(f"module-level decision decoders {sorted(decoders)} appeared without artifact binding")


def test_artifact_binding_fields_must_be_fingerprinted_when_they_appear():
    """An artifact binding outside context_fingerprint would be tamperable metadata."""
    present = _decision_field_names() & ARTIFACT_BINDING_FIELDS
    if not present:
        pytest.skip("no artifact binding yet; the guards above enforce that absence")
    payload_source = inspect.getsource(ValidatedTrajectoryDecision._payload)
    missing = sorted(field for field in present if f'"{field}"' not in payload_source)
    assert not missing, f"artifact binding fields absent from the fingerprinted payload: {missing}"


def test_execution_capability_registry_is_still_process_local():
    """The premise of these guards, asserted rather than assumed."""
    from singular.execution_capability import ExecutionCapabilityRegistry

    def authorized(action):
        return action

    original = ExecutionCapabilityRegistry()
    token = original.register(authorized, "cap_guard_probe")

    restarted = ExecutionCapabilityRegistry()
    assert restarted.matches(token, authorized) is False, (
        "a restarted registry recognised a token it never issued"
    )

    impostor = lambda action: action  # noqa: E731 - stands in for arbitrary attacker code
    assert restarted.register(impostor, token) == token
    assert restarted.matches(token, impostor) is True, (
        "registry semantics changed: re-registration under a durable token no longer "
        "binds an arbitrary object, so the restart bypass this file guards may be gone"
    )


def test_decision_binds_an_artifact_today():
    """The condition the guards above are protecting."""
    assert _binds_an_artifact() is True
    assert "execution_artifact_fingerprint" in _decision_field_names()
