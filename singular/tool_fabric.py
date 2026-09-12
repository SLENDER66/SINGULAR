from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any

from .autopilot import ActionRequest, ExecutionBus


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: float
    reversibility: float
    sensitive: bool = False
    requires_human: bool = False
    handler: Callable[..., Any] | None = None


class ToolFabric:
    """Registry + planning surface; execution requires the validated boundary."""

    def __init__(self):
        self.tools: dict[str, ToolSpec] = {}
        self.bus = ExecutionBus()

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self.tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self.tools[spec.name] = spec
