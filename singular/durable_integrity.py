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
                "SELECT execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until FROM executions ORDER BY execution_key"
            ).fetchall()
            effects = conn.execute(
                "SELECT provider_idempotency_key,execution_key,status,action_fingerprint FROM external_effects ORDER BY provider_idempotency_key"
            ).fetchall()

            execution_keys = {row["execution_key"] for row in executions}
            valid_execution_statuses = {"RUNNING", "RECOVERY_REQUIRED", "COMPLETED", "FAILED"}
            for row in executions:
                execution_status = row["status"]
                if execution_status not in valid_execution_statuses:
                    violations.append(IntegrityViolation("execution", row["execution_key"], "EXEC-STATUS", f"unknown execution status: {execution_status}"))
                    continue

                mission = conn.execute(
                    "SELECT status FROM mission_states WHERE mission_id=?", (row["mission_id"],)
                ).fetchone()
                if mission is None:
                    violations.append(IntegrityViolation("execution", row["execution_key"], "EXEC-MISSION", "execution references a missing mission state"))
                    continue
                mission_status = mission["status"]

                if execution_status == "RUNNING":
                    if row["finished_at"] is not None:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "RUNNING-FINISHED", "RUNNING execution must not have finished_at"))
                elif execution_status == "RECOVERY_REQUIRED":
                    if mission_status != MissionStatus.RUNNING.value:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "RECOVERY-MISSION", "RECOVERY_REQUIRED execution must keep its mission RUNNING"))
                    if row["lease_until"] is not None:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "RECOVERY-LEASE", "RECOVERY_REQUIRED execution must not retain an execution lease"))
                    if row["finished_at"] is None:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "RECOVERY-FINISHED", "RECOVERY_REQUIRED execution must record when it entered recovery"))
                elif execution_status == "COMPLETED":
                    if mission_status != MissionStatus.COMPLETED.value:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "COMPLETED-MISSION", "COMPLETED execution must have a COMPLETED mission"))
                    if row["finished_at"] is None or row["lease_until"] is not None:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "COMPLETED-LIFECYCLE", "COMPLETED execution must be finished and have no lease"))
                elif execution_status == "FAILED":
                    if mission_status not in {MissionStatus.FAILED.value, MissionStatus.CANCELLED.value}:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "FAILED-MISSION", "FAILED execution must have a FAILED or CANCELLED mission"))
                    if row["finished_at"] is None or row["lease_until"] is not None:
                        violations.append(IntegrityViolation("execution", row["execution_key"], "FAILED-LIFECYCLE", "FAILED execution must be finished and have no lease"))

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
