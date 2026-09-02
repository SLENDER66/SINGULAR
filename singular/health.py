from __future__ import annotations

from dataclasses import dataclass

from .autopilot import ExecutionBus
from .models import WorldModel


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    ready: bool
    checks: dict[str, bool]


def check_system(world: WorldModel, bus: ExecutionBus) -> HealthStatus:
    checks = {
        "world_model": world is not None,
        "execution_bus": bus is not None,
        "world_model_valid": world.version != "",
    }
    healthy = all(checks.values())
    return HealthStatus(healthy=healthy, ready=healthy, checks=checks)
