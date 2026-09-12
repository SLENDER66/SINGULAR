from singular.execution_capability import ExecutionCapabilityRegistry


def test_registry_binds_to_exact_object_identity():
    registry = ExecutionCapabilityRegistry()
    first = lambda _action: None
    second = lambda _action: None
    capability = registry.register(first, "cap_exact_object")

    assert registry.matches(capability, first) is True
    assert registry.matches(capability, second) is False


def test_registry_rejects_token_collision_and_supports_revoke():
    registry = ExecutionCapabilityRegistry()
    first = lambda _action: None
    second = lambda _action: None
    registry.register(first, "cap_collision")

    try:
        registry.register(second, "cap_collision")
    except ValueError:
        pass
    else:
        raise AssertionError("capability collision must be rejected")

    registry.revoke("cap_collision")
    assert registry.matches("cap_collision", first) is False
