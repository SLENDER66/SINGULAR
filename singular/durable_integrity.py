from __future__ import annotations

from dataclasses import dataclass

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
            # One snapshot for every table read here. Without it the executions
            # were read at one instant and each mission status at another, so a
            # writer finishing an execution between the two showed this scan a
            # RUNNING row under an already COMPLETED mission -- a contradiction
            # that never existed, reported as a broken database, refusing a
            # legitimate concurrent execution. The store runs in WAL, so a
            # deferred read transaction pins a consistent view without blocking
            # the writer.
            conn.execute("BEGIN")
            executions = conn.execute(
                "SELECT rowid,execution_key,mission_id,action_id,status,result,error,started_at,finished_at,lease_until "
                "FROM executions ORDER BY execution_key"
            ).fetchall()
            # One query rather than one per execution row: this scan runs before
            # every validated execution, so its cost is paid on the hot path and
            # grew with the whole history.
            missions = {
                row["mission_id"]: row["status"]
                for row in conn.execute("SELECT mission_id,status FROM mission_states")
            }
            effects = conn.execute(
                "SELECT provider_idempotency_key,execution_key,status,action_fingerprint FROM external_effects ORDER BY provider_idempotency_key"
            ).fetchall()

            execution_keys = {row["execution_key"] for row in executions}
            # A mission's terminal executions are history the moment it is
            # replanned. Only its most recent attempt says anything about where
            # the mission stands now: an action that failed, then a replanned
            # mission whose next action succeeded, is an ordinary sequence the
            # state machine allows on purpose (FAILED -> PLANNED), and reading
            # the older FAILED row against the mission's current COMPLETED
            # status called the database broken -- permanently, blocking every
            # future execution, over nothing.
            latest_execution = {}
            for row in executions:
                current = latest_execution.get(row["mission_id"])
                if current is None or row["rowid"] > current:
                    latest_execution[row["mission_id"]] = row["rowid"]
            valid_execution_statuses = {"RUNNING", "RECOVERY_REQUIRED", "COMPLETED", "FAILED"}
            for row in executions:
                key = row["execution_key"]
                mission_status = missions.get(row["mission_id"])
                if mission_status is None:
                    violations.append(IntegrityViolation("execution", key, "EXEC-MISSION", "execution references a missing mission state"))
                    continue

                execution_status = row["status"]
                if execution_status not in valid_execution_statuses:
                    violations.append(IntegrityViolation("execution", key, "EXEC-STATUS", f"unknown execution status: {execution_status}"))
                    continue
                # A live claim always constrains its mission, latest or not: an
                # execution still running under a finished mission is wrong
                # whatever came after it.
                is_latest = latest_execution.get(row["mission_id"]) == row["rowid"]
                if not row["started_at"]:
                    violations.append(IntegrityViolation("execution", key, "EXEC-START-TIME", "execution has no durable start timestamp"))
                if execution_status == "RUNNING":
                    if row["finished_at"] is not None:
                        violations.append(IntegrityViolation("execution", key, "RUNNING-FINISHED", "RUNNING execution cannot have a finished_at timestamp"))
                    if mission_status != MissionStatus.RUNNING.value:
                        violations.append(IntegrityViolation("execution", key, "RUNNING-MISSION", "RUNNING execution must have a RUNNING mission"))
                elif execution_status == "RECOVERY_REQUIRED":
                    if row["finished_at"] is None:
                        violations.append(IntegrityViolation("execution", key, "RECOVERY-FINISHED", "RECOVERY_REQUIRED execution must retain a recovery timestamp"))
                    if row["lease_until"] is not None:
                        violations.append(IntegrityViolation("execution", key, "RECOVERY-LEASE", "RECOVERY_REQUIRED execution cannot retain an active lease"))
                    if mission_status != MissionStatus.RUNNING.value:
                        violations.append(IntegrityViolation("execution", key, "RECOVERY-MISSION", "RECOVERY_REQUIRED execution must keep its mission RUNNING"))
                elif execution_status == "COMPLETED":
                    if row["finished_at"] is None:
                        violations.append(IntegrityViolation("execution", key, "COMPLETED-FINISHED", "COMPLETED execution must have a finished_at timestamp"))
                    if row["lease_until"] is not None:
                        violations.append(IntegrityViolation("execution", key, "COMPLETED-LEASE", "COMPLETED execution cannot retain an active lease"))
                    if is_latest and mission_status != MissionStatus.COMPLETED.value:
                        violations.append(IntegrityViolation("execution", key, "COMPLETED-MISSION", "COMPLETED execution must have a COMPLETED mission"))
                elif execution_status == "FAILED":
                    if row["finished_at"] is None:
                        violations.append(IntegrityViolation("execution", key, "FAILED-FINISHED", "FAILED execution must have a finished_at timestamp"))
                    if row["lease_until"] is not None:
                        violations.append(IntegrityViolation("execution", key, "FAILED-LEASE", "FAILED execution cannot retain an active lease"))
                    if is_latest and mission_status not in {MissionStatus.FAILED.value, MissionStatus.CANCELLED.value}:
                        violations.append(IntegrityViolation("execution", key, "FAILED-MISSION", "FAILED execution must have a FAILED or CANCELLED mission"))

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
