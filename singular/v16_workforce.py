from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .empire import AgentRegistry, AgentSpec, AutopilotSupervisor


DEFAULT_WORKFORCE = (
    ('INTELLIGENCE', 'Research, verify and synthesize information.', ('research', 'web', 'files'), 1),
    ('STRATEGY', 'Turn goals into robust strategies.', ('strategy', 'decision'), 2),
    ('CAREER', 'Handle career research and application preparation.', ('career', 'research'), 1),
    ('FINANCE', 'Analyze finances, budgets and patrimony decisions.', ('finance', 'decision'), 2),
    ('BUSINESS', 'Explore and test revenue opportunities.', ('business', 'opportunity'), 2),
    ('CAPABILITY', 'Design skill acquisition and practice systems.', ('learning', 'capability'), 1),
    ('LIFE', 'Optimize organization, routines and sustainable life structure.', ('life', 'planning'), 1),
    ('MENTAL', 'Track functional mental state, recovery, cognitive load and psychological resilience; adapt plans without diagnosing or replacing professional care.', ('mental_state', 'recovery', 'self_regulation'), 1),
    ('PRESENCE', 'Develop physical capacity, posture, presentation, voice, communication and social presence.', ('physical', 'presence', 'communication', 'social'), 1),
    ('RED_TEAM', 'Attack assumptions and proposed plans.', ('red_team', 'decision'), 3),
    ('SYSTEM_ARCHITECT', 'Audit and improve SINGULAR itself.', ('architecture', 'evals'), 3),
)


def build_default_registry(handlers: dict[str, Callable[[dict[str, Any]], Any]] | None = None) -> AgentRegistry:
    handlers = handlers or {}
    reg = AgentRegistry()
    for name, mission, caps, tier in DEFAULT_WORKFORCE:
        reg.register(AgentSpec(name, mission, caps, tier, handlers.get(name)))
    return reg


@dataclass
class WorkforceResult:
    selected: list[str]
    missing_capabilities: list[str]


class WorkforcePlanner:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def plan(self, capabilities: list[str]) -> WorkforceResult:
        selected, missing = [], []
        for cap in capabilities:
            agents = self.registry.available(cap)
            if agents:
                selected.append(min(agents, key=lambda a: a.risk_tier).name)
            else:
                missing.append(cap)
        return WorkforceResult(list(dict.fromkeys(selected)), missing)
