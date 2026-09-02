from __future__ import annotations
from datetime import datetime, timezone
from .agents import Commander
from .models import Action, Decision, WorldModel

class SingularRuntime:
    def __init__(self, world: WorldModel | None = None):
        self.world = world or WorldModel()
        self.commander = Commander()

    def snapshot(self) -> dict:
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'world_version': self.world.version,
            'objectives': len(self.world.objectives),
            'opportunities': len(self.world.opportunities),
            'risks': len(self.world.risks),
            'decisions': len(self.world.decisions),
            'learnings': len(self.world.learnings),
        }

    def next_action(self, actions: list[Action]) -> dict:
        result = self.commander.triage(actions)
        return result

    def evaluate_decision(self, decision: Decision, consequence=5, reversibility=5) -> dict:
        result = self.commander.decide(decision, consequence, reversibility)
        self.world.decisions.append(decision)
        return result
