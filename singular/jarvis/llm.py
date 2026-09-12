"""Provider boundary for JARVIS reasoning.

The provider proposes structured work; SINGULAR remains the authority that
routes, governs and executes it. No provider object is allowed to execute a
SINGULAR action directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: LLMUsage = LLMUsage()
    model: str = ""


class LLMProvider(Protocol):
    """Minimal reasoning contract used by JARVIS."""

    def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse:
        """Return model text; no execution authority is implied."""


class LLMProviderError(RuntimeError):
    """A provider could not produce a response."""


class AnthropicProvider:
    """Anthropic Claude adapter with secrets confined to the environment.

    The SDK is imported lazily so the governed core and all tests can run
    without the optional provider package or an API key.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any = None,
        timeout: float = 60.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("JARVIS_LLM_MODEL", "claude-opus-5")
        self.timeout = timeout
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY is not configured")
        try:
            import anthropic
        except ImportError as exc:
            raise LLMProviderError("The anthropic package is not installed") from exc
        self._client = anthropic.Anthropic(api_key=self._api_key, timeout=self.timeout)
        return self._client

    def complete(self, *, system: str, user: str, max_tokens: int) -> LLMResponse:
        if not system.strip() or not user.strip():
            raise ValueError("system and user prompts must not be blank")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        try:
            response = self._client_or_create().messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            # Do not expose SDK exception text: depending on SDK/version it may
            # contain request metadata or authentication material.
            raise LLMProviderError("Anthropic request failed") from None

        text = "\n".join(
            block.text for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            usage=LLMUsage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            ),
            model=str(getattr(response, "model", self.model)),
        )


__all__ = ["AnthropicProvider", "LLMProvider", "LLMProviderError", "LLMResponse", "LLMUsage"]
