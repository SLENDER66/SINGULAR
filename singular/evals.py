from __future__ import annotations
from dataclasses import dataclass
from .mission_autopilot import Mission

@dataclass(frozen=True)
class MissionEval:
    completion: float
    human_load: float
    safety: float
    score: float

def evaluate_mission(mission: Mission) -> MissionEval:
    n = len(mission.steps) or 1
    done = sum(s.status.value == 'DONE' for s in mission.steps)
    blocked = sum(s.status.value == 'BLOCKED' for s in mission.steps)
    completion = done / n
    human_load = blocked / n
    safety = 1.0 if all('HALT' not in (s.error or '') or s.status.value == 'BLOCKED' for s in mission.steps) else 0.0
    score = 0.55 * completion + 0.25 * (1-human_load) + 0.20 * safety
    return MissionEval(completion, human_load, safety, score)
