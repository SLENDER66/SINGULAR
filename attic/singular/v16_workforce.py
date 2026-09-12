from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .elite import EliteEngine, EliteReview, EliteScore
from .empire import AgentRegistry, AgentSpec, AutopilotSupervisor


DEFAULT_WORKFORCE = (
    ('COMMANDER', 'Focus the objective, choose the best next move and keep the system simple.', ('command', 'prioritization', 'coordination'), 2),
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
    elite_reviews: list[EliteReview] | None = None
    challenges: list[dict[str, str]] | None = None


class WorkforcePlanner:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def plan(
        self,
        capabilities: list[str],
        *,
        elite_scores: dict[str, EliteScore] | None = None,
        challenge: bool = False,
    ) -> WorkforceResult:
        selected, missing = [], []
        for cap in capabilities:
            agents = self.registry.available(cap)
            if agents:
                selected.append(min(agents, key=lambda a: a.risk_tier).name)
            else:
                missing.append(cap)

        selected = list(dict.fromkeys(selected))
        scores = elite_scores or {}
        reviews = [EliteEngine.review(name, scores[name]) for name in selected if name in scores]
        challenges = [EliteEngine.challenge(review.agent, review) for review in reviews] if challenge else []
        return WorkforceResult(selected, missing, reviews, challenges)
