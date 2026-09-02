from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
from typing import Callable, Any

from .autopilot import ActionRequest, DelegationContract, ExecutionBus, Governor, Autonomy

class StepStatus(str, Enum):
    PENDING='PENDING'; READY='READY'; RUNNING='RUNNING'; DONE='DONE'; BLOCKED='BLOCKED'; FAILED='FAILED'

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
    """Turns a mission into a dependency-aware execution plan.

    It never bypasses the Governor: sensitive, irreversible, or unauthorized actions
    become approvals/blockers instead of being executed.
    """
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
        # Dependencies can be step IDs or step names.
        return all(dep in done or any(s.name == dep and s.status == StepStatus.DONE for s in mission.steps) for dep in step.depends_on)

    def run(self, mission: Mission) -> Mission:
        mission.status = StepStatus.RUNNING
        progress = True
        while progress:
            progress = False
            for step in mission.steps:
                if step.status in (StepStatus.DONE, StepStatus.BLOCKED, StepStatus.FAILED):
                    continue
                if not self._ready(step, mission):
                    continue
                decision = self.bus.submit(step.action, mission.contract)
                if decision.mode in (Autonomy.ESCALATE, Autonomy.PREPARE, Autonomy.BLOCK):
                    step.status = StepStatus.BLOCKED
                    step.error = '; '.join(decision.reasons)
                    progress = True
                    continue
                handler = self.handlers.get(step.action.name)
                if handler is None:
                    step.status = StepStatus.BLOCKED
                    step.error = 'Aucun handler d’exécution enregistré.'
                    progress = True
                    continue
                step.status = StepStatus.RUNNING
                try:
                    step.result = handler(step.action)
                    step.status = StepStatus.DONE
                except Exception as exc:
                    step.status = StepStatus.FAILED
                    step.error = str(exc)
                progress = True
        if all(s.status == StepStatus.DONE for s in mission.steps):
            mission.status = StepStatus.DONE
        elif any(s.status == StepStatus.FAILED for s in mission.steps):
            mission.status = StepStatus.FAILED
        else:
            mission.status = StepStatus.BLOCKED
        return mission

    @staticmethod
    def human_load(mission: Mission) -> dict[str, int]:
        return {
            'total_steps': len(mission.steps),
            'done': sum(s.status == StepStatus.DONE for s in mission.steps),
            'blocked': sum(s.status == StepStatus.BLOCKED for s in mission.steps),
            'failed': sum(s.status == StepStatus.FAILED for s in mission.steps),
        }
