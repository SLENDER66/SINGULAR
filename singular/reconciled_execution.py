from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .durable import DurableStore, MissionStatus
from .effects import EffectStatus


@dataclass(frozen=True)
class ReconciledExecution:
    execution_key: str
    mission_id: str
    action_id: str
    result: Any
