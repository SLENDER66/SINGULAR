import pytest

from singular.config import Settings
from singular.logging_utils import redact
from singular.production_runtime import AgentsSDKRuntime


def test_production_requires_api_key(monkeypatch):
    monkeypatch.setenv("SINGULAR_ENV", "production")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        Settings.from_env().validate()


def test_redaction_hides_common_secrets():
    text = "OPENAI_API_KEY=sk-EXAMPLE-REDACTED"
    assert "abcdefghijklmnopqrstuvwxyz" not in redact(text)
    assert "[REDACTED]" in redact(text)


def test_runtime_rejects_live_execution_without_key():
    runtime = AgentsSDKRuntime(Settings())
    if runtime.status.sdk_available:
        agent = runtime.build_commander()
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            runtime.run_sync(agent, "hello")


def test_runtime_rejects_invalid_turn_limit():
    runtime = AgentsSDKRuntime(Settings(openai_api_key="test-key"))
    if runtime.status.sdk_available:
        agent = runtime.build_commander()
        with pytest.raises(ValueError):
            runtime.run_sync(agent, "hello", max_turns=0)
