from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings


@dataclass(frozen=True)
class RuntimeStatus:
    sdk_available: bool
    configured: bool
    model: str


class AgentsSDKRuntime:
    """Controlled boundary around the OpenAI Agents SDK.

    SINGULAR's domain logic remains usable without the SDK. This boundary owns
    agent construction and execution so provider/runtime concerns do not leak
    into the core decision model.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._sdk: Any | None = None
        try:
            import agents
            self._sdk = agents
        except ImportError:
            self._sdk = None

    @property
    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            sdk_available=self._sdk is not None,
            configured=bool(self.settings.openai_api_key),
            model=self.settings.openai_model,
        )

    def require_sdk(self) -> Any:
        if self._sdk is None:
            raise RuntimeError(
                "OpenAI Agents SDK absent. Install the optional 'runtime' dependency."
            )
        return self._sdk

    def require_configured(self) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for live agent execution.")

    def build_commander(self, *, instructions: str | None = None) -> Any:
        """Build the SINGULAR Commander without performing a model call."""
        sdk = self.require_sdk()
        return sdk.Agent(
            name="SINGULAR_COMMANDER",
            instructions=instructions or (
                "You are SINGULAR's Commander. Preserve the user's objectives and "
                "governance rules. Prefer reversible, evidence-based actions. "
                "Escalate sensitive, irreversible, financial, legal, contractual, "
                "or high-impact actions for human validation."
            ),
            model=self.settings.openai_model,
        )

    def run_sync(self, agent: Any, input_text: str, *, max_turns: int = 8) -> Any:
        """Execute an agent only after explicit runtime configuration checks."""
        self.require_sdk()
        self.require_configured()
        if not input_text.strip():
            raise ValueError("input_text must not be empty")
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        return self._sdk.Runner.run_sync(agent, input_text, max_turns=max_turns)
