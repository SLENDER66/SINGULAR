from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4
from datetime import datetime, timezone

from .autopilot import ActionRequest, DelegationContract, ExecutionBus, Governor, Autonomy

class EventType(str, Enum):
    USER='USER'; EMAIL='EMAIL'; CALENDAR='CALENDAR'; WEB='WEB'; FILE='FILE'; SYSTEM='SYSTEM'; RESULT='RESULT'; ALERT='ALERT'

@dataclass(frozen=True)
class Event:
    type: EventType
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: 'EVT-' + uuid4().hex[:10])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class AgentSpec:
    name: str
    mission: str
    capabilities: tuple[str, ...]
    risk_tier: int = 1
    handler: Optional[Callable[[dict[str, Any]], Any]] = None
    enabled: bool = True

@dataclass
class MissionRun:
    mission_id: str
    objective: str
    status: str = 'QUEUED'
    outputs: list[Any] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    human_requests: list[str] = field(default_factory=list)

class AgentRegistry:
    def __init__(self): self.agents: dict[str, AgentSpec] = {}
    def register(self, spec: AgentSpec):
        if spec.name in self.agents: raise ValueError(f'Agent already registered: {spec.name}')
        self.agents[spec.name] = spec
    def available(self, capability: str) -> list[AgentSpec]:
        return [a for a in self.agents.values() if a.enabled and capability in a.capabilities]

class EventBus:
    def __init__(self): self.events: list[Event] = []; self.handlers: list[Callable[[Event], Any]] = []
    def subscribe(self, handler): self.handlers.append(handler)
    def publish(self, event: Event):
        self.events.append(event)
        return [h(event) for h in self.handlers]

class HumanLoadOptimizer:
    @staticmethod
    def score(requests: int, steps: int) -> float:
        if steps <= 0: return 0.0
        return round(requests / steps, 3)

class AutopilotSupervisor:
    """Closed-loop supervisor: observe events, route missions, execute safe work, escalate the rest."""
    def __init__(self, registry: AgentRegistry | None = None):
        self.registry = registry or AgentRegistry()
        self.events = EventBus()
        self.bus = ExecutionBus()
        self.runs: dict[str, MissionRun] = {}
        self.audit: list[dict[str, Any]] = []
        self.events.subscribe(self._audit_event)

    def _audit_event(self, event: Event):
        self.audit.append({'event_id': event.id, 'type': event.type.value, 'name': event.name, 'created_at': event.created_at})

    def create_run(self, objective: str) -> MissionRun:
        run = MissionRun('RUN-' + uuid4().hex[:10], objective)
        self.runs[run.mission_id] = run
        return run

    def route(self, run: MissionRun, capability: str, payload: dict[str, Any]) -> Any:
        candidates = self.registry.available(capability)
        if not candidates:
            run.blockers.append(f'Aucun agent pour la capacité: {capability}')
            run.status = 'BLOCKED'
            return None
        agent = sorted(candidates, key=lambda a: a.risk_tier)[0]
        self.events.publish(Event(EventType.SYSTEM, 'agent_selected', {'agent': agent.name, 'run': run.mission_id}))
        if agent.handler is None:
            run.human_requests.append(f'Configurer le handler de {agent.name}')
            run.status = 'WAITING_HUMAN'
            return None
        try:
            out = agent.handler(payload)
            run.outputs.append({'agent': agent.name, 'output': out})
            self.events.publish(Event(EventType.RESULT, 'agent_result', {'run': run.mission_id, 'agent': agent.name}))
            return out
        except Exception as exc:
            run.blockers.append(str(exc)); run.status = 'FAILED'; return None

    def finish(self, run: MissionRun):
        run.status = 'DONE' if not run.blockers and not run.human_requests else ('WAITING_HUMAN' if run.human_requests else 'BLOCKED')
        return run

class EmpireLoop:
    """High-level loop for continuous operation without granting unsafe permissions."""
    def __init__(self, supervisor: AutopilotSupervisor): self.supervisor = supervisor
    def tick(self, events: list[Event]) -> list[Any]:
        results = []
        for event in events:
            results.extend(self.supervisor.events.publish(event))
        return results
