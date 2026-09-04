from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .sqlite_support import SqliteLocation


@dataclass(frozen=True)
class ConsistencyViolation:
    code: str
    message: str
    execution_key: str | None = None
    mission_id: str | None = None


class CrossDomainConsistencyError(RuntimeError):
    """Durable mission/execution/external-effect state violates an invariant."""


class CrossDomainConsistencyChecker:
    """Read-only invariant checker for the mission/execution/effect state graph."""

    def __init__(self, db_path: str | Path) -> None:
        self._location = SqliteLocation(db_path)
        self.db_path = self._location.reference

    def check(self, mission_id: str | None = None) -> tuple[ConsistencyViolation, ...]:
        with self._location.connect() as conn:
            conn.row_factory = sqlite3.Row
            mission_filter = " AND e.mission_id=?" if mission_id is not None else ""
            params = (mission_id,) if mission_id is not None else ()
            executions = conn.execute(
                "SELECT e.execution_key,e.mission_id,e.action_id,e.status AS execution_status, m.status AS mission_status "
                "FROM executions e JOIN mission_states m ON m.mission_id=e.mission_id" + mission_filter,
                params,
            ).fetchall()
            violations: list[ConsistencyViolation] = []
            has_effect_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='external_effects'").fetchone() is not None
            for execution in executions:
                key, mid = execution["execution_key"], execution["mission_id"]
                execution_status, mission_status = execution["execution_status"], execution["mission_status"]
                if mission_status == "COMPLETED" and execution_status != "COMPLETED":
                    violations.append(ConsistencyViolation("MISSION_COMPLETED_WITH_NONTERMINAL_EXECUTION", "Une mission COMPLETED doit avoir une exécution COMPLETED.", key, mid))
                if execution_status == "COMPLETED" and mission_status != "COMPLETED":
                    violations.append(ConsistencyViolation("EXECUTION_COMPLETED_WITH_NONCOMPLETED_MISSION", "Une exécution COMPLETED doit terminer la mission correspondante.", key, mid))
                if execution_status == "RECOVERY_REQUIRED" and mission_status == "COMPLETED":
                    violations.append(ConsistencyViolation("RECOVERY_EXECUTION_WITH_COMPLETED_MISSION", "Une exécution RECOVERY_REQUIRED ne peut pas être rattachée à une mission COMPLETED.", key, mid))
                if not has_effect_table:
                    continue
                effects = conn.execute("SELECT provider_idempotency_key,status FROM external_effects WHERE execution_key=?", (key,)).fetchall()
                for effect in effects:
                    effect_status = effect["status"]
                    if execution_status == "COMPLETED" and effect_status != "COMPLETED":
                        violations.append(ConsistencyViolation("EXECUTION_COMPLETED_WITH_NONTERMINAL_EFFECT", "Une exécution COMPLETED ne peut pas rester rattachée à un effet externe non terminé.", key, mid))
                    if mission_status == "COMPLETED" and effect_status != "COMPLETED":
                        violations.append(ConsistencyViolation("MISSION_COMPLETED_WITH_NONCOMPLETED_EFFECT", "Une mission COMPLETED ne peut pas masquer un effet externe non terminé.", key, mid))
                    if effect_status == "COMPLETED" and execution_status in {"FAILED", "RECOVERY_REQUIRED"}:
                        violations.append(ConsistencyViolation("COMPLETED_EFFECT_WITH_UNRESOLVED_EXECUTION", "Un effet externe COMPLETED ne peut pas rester rattaché à une exécution FAILED ou RECOVERY_REQUIRED.", key, mid))
            return tuple(violations)

    def assert_consistent(self, mission_id: str | None = None) -> None:
        violations = self.check(mission_id)
        if violations:
            details = "; ".join(v.code for v in violations)
            raise CrossDomainConsistencyError(f"Invariants durables violés : {details}")
