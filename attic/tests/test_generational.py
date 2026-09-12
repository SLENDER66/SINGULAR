import pytest

from singular.generational import GenerationalCharter, GenerationalEngine


def test_generational_system_requires_portable_institution() -> None:
    charter = GenerationalCharter(
        generation=1,
        mission="Build and transmit durable productive wealth",
        governance_documented=True,
        knowledge_portable=True,
        audit_restorable=True,
        successor_defined=True,
    )
    result = GenerationalEngine.assess(
        charter,
        capital_protection=0.9,
        founder_independence=0.9,
        institutional_resilience=0.9,
    )
    assert result.ready is True
    assert result.priorities == ()


def test_missing_continuity_components_are_explicit_priorities() -> None:
    charter = GenerationalCharter(1, "Build durable wealth")
    result = GenerationalEngine.assess(
        charter,
        capital_protection=0.5,
        founder_independence=0.5,
        institutional_resilience=0.5,
    )
    assert result.ready is False
    assert "DEFINE_SUCCESSION" in result.priorities
    assert "REMOVE_FOUNDER_SINGLE_POINT_OF_FAILURE" in result.priorities
    assert "PROTECT_PATRIMONY" in result.priorities


def test_generation_and_mission_are_validated() -> None:
    with pytest.raises(ValueError):
        GenerationalCharter(0, "Build")
    with pytest.raises(ValueError):
        GenerationalCharter(1, "")
