from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
from typing import Callable, Any

from .autopilot import ActionRequest, DelegationContract, ExecutionBus


class StepStatus(str, Enum):
    PENDING = 'PENDING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    DONE = 'DONE'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'


@dataclass
class MissionStep:
    name: str
    action: ActionRequest
    depends_on: tuple[str, ...] = ()
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    id: str = field(default_factory=lambda: 'STEP-' + uuid4().hex[:8])


@dataclass
class Mission:
    objective: str
    expected_result: str
    contract: DelegationContract
    steps: list[MissionStep] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    id: str = field(default_factory=lambda: 'MISRUN-' + uuid4().hex[:8])


class MissionAutopilot:
    """Build dependency-aware plans; execution is delegated to the validated boundary."""

    def __init__(self, bus: ExecutionBus | None = None):
        self.bus = bus or ExecutionBus()
        self.handlers: dict[str, Callable[[ActionRequest], Any]] = {}

    def register_handler(self, action_name: str, handler: Callable[[ActionRequest], Any]) -> None:
        self.handlers[action_name] = handler

    def plan(self, mission: Mission, actions: list[tuple[ActionRequest, tuple[str, ...]]]) -> Mission:
        mission.steps = [MissionStep(name=a.name, action=a, depends_on=deps) for a, deps in actions]
        mission.status = StepStatus.READY if mission.steps else StepStatus.BLOCKED
        return mission

    def _ready(self, step: MissionStep, mission: Mission) -> bool:
        done = {s.id for s in mission.steps if s.status == StepStatus.DONE}
        return all(
            dep in done or any(s.name == dep and s.status == StepStatus.DONE for s in mission.steps)
            for dep in step.depends_on
        )

    def run(self, mission: Mission) -> Mission:
        """Refuse legacy direct execution; only validated decisions may reach handlers."""
        mission.status = StepStatus.BLOCKED
        for step in mission.steps:
            if step.status in (StepStatus.DONE, StepStatus.BLOCKED, StepStatus.FAILED):
                continue
            step.status = StepStatus.BLOCKED
            step.error = 'Execution refusée: une ValidatedTrajectoryDecision est requise.'
        return mission

    @staticmethod
    def human_load(mission: Mission) -> dict[str, int]:
        return {
            'total_steps': len(mission.steps),
            'done': sum(s.status == StepStatus.DONE for s in mission.steps),
            'blocked': sum(s.status == StepStatus.BLOCKED for s in mission.steps),
            'failed': sum(s.status == StepStatus.FAILED for s in mission.steps),
        }
