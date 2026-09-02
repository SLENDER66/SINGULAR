from __future__ import annotations
from dataclasses import dataclass
from .autopilot import MissionManager

@dataclass
class Cockpit:
    mission_manager: MissionManager

    def snapshot(self) -> dict:
        pending = self.mission_manager.bus.pending()
        return {
            "status": "AUTOPILOT",
            "pending_approvals": [
                {"id": a.id, "action_id": a.action_id, "reason": a.reason}
                for a in pending
            ],
            "completed_actions": list(self.mission_manager.bus.completed),
            "human_load": len(pending),
        }

    def human_queue(self) -> list[dict]:
        return self.snapshot()["pending_approvals"]
