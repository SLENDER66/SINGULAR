from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any

from .autopilot import ActionRequest, ExecutionBus, Autonomy, ApprovalStatus


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

    def plan(self, name: str, description: str, contract=None):
        spec = self.tools[name]
        action = ActionRequest(
            name=name,
            description=description,
            impact=max(1.0, 10.0 - spec.risk),
            risk=spec.risk,
            reversibility=spec.reversibility,
            requires_human=spec.requires_human,
            sensitive=spec.sensitive,
            contract_id=contract.mission_id if contract else None,
        )
        return action, self.bus.submit(action, contract)

    def execute_approved(self, approval_id: str, name: str, **kwargs):
        """Legacy execution entry point deliberately disabled.

        Approval IDs and tool names are not sufficient authorization artifacts:
        the approved action, payload, contract, trajectory and governance context
        must be bound together by ValidatedTrajectoryDecision.
        """
        raise PermissionError(
            "Direct ToolFabric execution is disabled: use ValidatedTrajectoryDecision."
        )

    def execute_autonomous(self, name: str, contract=None, **kwargs):
        """Legacy autonomous execution entry point deliberately disabled."""
        raise PermissionError(
            "Direct ToolFabric execution is disabled: use ValidatedTrajectoryDecision."
        )
