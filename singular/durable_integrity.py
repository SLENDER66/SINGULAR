from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .durable import DurableStore, MissionStatus
from .effects import EffectStatus


@dataclass(frozen=True)
class IntegrityViolation:
    entity: str
    key: str
    rule: str
    detail: str


@dataclass(frozen=True)
class DurableIntegrityReport:
    violations: tuple[IntegrityViolation, ...]

    @property
    def clean(self) -> bool:
        return not self.violations


class DurableIntegrityChecker:
    """Detect impossible cross-table states without repairing them automatically."""

    def __init__(self, store: DurableStore) -> None:
        self.store = store

    def check(self) -> DurableIntegrityReport:
        violations: list[IntegrityViolation] = []
        with self.store._connect() as conn:
            executions = conn.execute(
                "SELECT execution_key,mission_id,action_id,status FROM executions ORDER BY execution_key"
            ).fetchall()
            effects = conn.execute(
                "SELECT provider_idempotency_key,execution_key,status,action_fingerprint FROM external_effects ORDER BY provider_idempotency_key"
            ).fetchall()

            execution_keys = {row["execution_key"] for row in executions}
            for row in executions:
                mission = conn.execute(
                    "SELECT status FROM mission_states WHERE mission_id=?", (row["mission_id"],)
                ).fetchone()
                if mission is None:
                    violations.append(IntegrityViolation("execution", row["execution_key"], "EXEC-MISSION", "execution references a missing mission state"))
                    continue
                execution_status = row["status"]
                mission_status = mission["status"]
                if execution_status == "RECOVERY_REQUIRED" and mission_status != MissionStatus.RUNNING.value:
                    violations.append(IntegrityViolation("execution", row["execution_key"], "RECOVERY-MISSION", "RECOVERY_REQUIRED execution must keep its mission RUNNING"))
                if execution_status == "COMPLETED" and mission_status != MissionStatus.COMPLETED.value:
                    violations.append(IntegrityViolation("execution", row["execution_key"], "COMPLETED-MISSION", "COMPLETED execution must have a COMPLETED mission"))
                if execution_status == "FAILED" and mission_status not in {MissionStatus.FAILED.value, MissionStatus.CANCELLED.value}:
                    violations.append(IntegrityViolation("execution", row["execution_key"], "FAILED-MISSION", "FAILED execution must have a FAILED or CANCELLED mission"))

            valid_effect_statuses = {status.value for status in EffectStatus}
            for row in effects:
                if row["execution_key"] not in execution_keys:
                    violations.append(IntegrityViolation("external_effect", row["provider_idempotency_key"], "EFFECT-EXECUTION", "external effect references a missing execution"))
                if row["status"] not in valid_effect_statuses:
                    violations.append(IntegrityViolation("external_effect", row["provider_idempotency_key"], "EFFECT-STATUS", f"unknown external effect status: {row['status']}"))
                if not row["action_fingerprint"]:
                    violations.append(IntegrityViolation("external_effect", row["provider_idempotency_key"], "EFFECT-ACTION-BINDING", "external effect has no action identity fingerprint"))

        return DurableIntegrityReport(tuple(violations))

    def assert_clean(self) -> None:
        report = self.check()
        if not report.clean:
            details = "; ".join(f"{item.entity}:{item.key}:{item.rule}: {item.detail}" for item in report.violations)
            raise RuntimeError(f"Durable state integrity failure: {details}")


__all__ = ["IntegrityViolation", "DurableIntegrityReport", "DurableIntegrityChecker"]
