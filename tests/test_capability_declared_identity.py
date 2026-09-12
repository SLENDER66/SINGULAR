"""An artifact's configuration, not only its class.

The capability fingerprint hashes a class's method bytecode, which is identical
for every instance of it. Two HttpEffectProvider objects pointing at different
endpoints were therefore the same artifact: after a restart, re-registering the
token against an instance aimed somewhere else satisfied the durable record and
the decision that named it. An artifact can now declare what makes it the one
that was authorized.
"""
import pytest

from singular.execution_capability import DurableCapabilityStore, artifact_fingerprint
from singular.providers.http_effect import HttpEffectProvider


class Undeclared:
    def execute(self, request, idempotency_key):
        return None


class Broken:
    def artifact_identity(self):
        raise RuntimeError("configuration unavailable")


class DeclaresNothing:
    def artifact_identity(self):
        return None


def _provider(endpoint="https://api.example.test/effects", **kwargs) -> HttpEffectProvider:
    return HttpEffectProvider(endpoint, **kwargs)


def test_two_instances_without_a_declaration_stay_indistinguishable(tmp_path):
    """The stated limit, kept visible: silence is not covered."""
    assert artifact_fingerprint(Undeclared()) == artifact_fingerprint(Undeclared())


def test_a_declared_configuration_distinguishes_two_instances():
    assert artifact_fingerprint(_provider()) != artifact_fingerprint(_provider("https://elsewhere.test/effects"))


def test_the_same_configuration_is_the_same_artifact_after_a_restart():
    """A legitimate restart re-registers an equivalent instance and must be accepted."""
    assert artifact_fingerprint(_provider()) == artifact_fingerprint(_provider())


def test_a_differently_configured_provider_cannot_take_over_the_token(tmp_path):
    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    store.bind("cap_http", _provider())

    with pytest.raises(PermissionError, match="different executable artifact"):
        store.bind("cap_http", _provider("https://elsewhere.test/effects"))

    assert store.verify("cap_http", _provider()) is True
    assert store.verify("cap_http", _provider("https://elsewhere.test/effects")) is False


def test_the_reconcile_endpoint_is_part_of_the_identity(tmp_path):
    """Where an ambiguous effect is resolved is as authorized as where it is sent."""
    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    store.bind("cap_http", _provider(reconcile_endpoint="https://api.example.test/status"))

    with pytest.raises(PermissionError, match="different executable artifact"):
        store.bind("cap_http", _provider(reconcile_endpoint="https://elsewhere.test/status"))


def test_rotating_a_credential_does_not_revoke_the_artifact():
    """The endpoint is what the authorization is about, not the secret used with it."""
    rotated = _provider(headers={"Authorization": "Bearer new"})
    assert artifact_fingerprint(_provider(headers={"Authorization": "Bearer old"})) == artifact_fingerprint(rotated)
    assert artifact_fingerprint(rotated) != artifact_fingerprint(_provider(headers={"Authorization": "Bearer new", "X-Extra": "1"}))


def test_a_declaration_that_cannot_be_produced_is_refused(tmp_path):
    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    with pytest.raises(ValueError, match="artifact identity could not be established"):
        artifact_fingerprint(Broken())
    with pytest.raises(ValueError, match="declared nothing"):
        artifact_fingerprint(DeclaresNothing())

    store.bind("cap_ok", Undeclared())
    assert store.verify("cap_ok", Broken()) is False
