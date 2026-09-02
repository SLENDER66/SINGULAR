from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any
from .autopilot import ActionRequest, ExecutionBus, Governor, Autonomy, ApprovalStatus

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
    """Registry + policy boundary. Tools never execute before policy evaluation."""
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
            name=name, description=description, impact=max(1.0, 10.0-spec.risk),
            risk=spec.risk, reversibility=spec.reversibility,
            requires_human=spec.requires_human, sensitive=spec.sensitive,
            contract_id=contract.mission_id if contract else None,
        )
        return action, self.bus.submit(action, contract)

    def execute_approved(self, approval_id: str, name: str, **kwargs):
        approval = self.bus.approvals[approval_id]
        if approval.status != ApprovalStatus.APPROVED:
            raise PermissionError("Tool execution requires an approved action.")
        spec = self.tools[name]
        if spec.handler is None:
            raise RuntimeError(f"No handler registered for {name}")
        result = spec.handler(**kwargs)
        self.bus.completed.append(approval.action_id)
        return result

    def execute_autonomous(self, name: str, contract=None, **kwargs):
        action, decision = self.plan(name, f"Execute {name}", contract)
        if decision.mode not in (Autonomy.EXECUTE_REVERSIBLE, Autonomy.EXECUTE_AUTHORIZED):
            raise PermissionError(f"Autonomous execution denied: {decision.mode}")
        spec = self.tools[name]
        if spec.handler is None:
            raise RuntimeError(f"No handler registered for {name}")
        result = spec.handler(**kwargs)
        self.bus.completed.append(action.id)
        return result
