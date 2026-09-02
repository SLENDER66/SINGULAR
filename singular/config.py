from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"
    openai_model: str = "gpt-5.6"
    openai_api_key: str | None = None
    tracing_enabled: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("SINGULAR_ENV", "development").strip().lower(),
            log_level=os.getenv("SINGULAR_LOG_LEVEL", "INFO").strip().upper(),
            openai_model=os.getenv("SINGULAR_OPENAI_MODEL", "gpt-5.6").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            tracing_enabled=os.getenv("SINGULAR_TRACING", "false").lower() in {"1", "true", "yes", "on"},
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate(self) -> None:
        if not self.openai_model:
            raise ValueError("SINGULAR_OPENAI_MODEL must not be empty")
        if self.is_production and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required in production")
