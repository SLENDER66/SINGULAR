from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Callable

from cryptography.fernet import Fernet

from .audit import AuditEvent, AuditTrail
from .authority import AgentPower, AuthorityProtocol
from .authentication import AuthenticationError, AuthenticationService, RateLimited, SecondFactorRequired, _totp
from .durable import DurableStore
from .economic_learning import EconomicLearningEngine
from .economic_learning_ledger import EconomicLearningLedger
from .execution_result import (
    ExecutionIntent,
    ExecutionResult,
    ExecutionResultBridge,
    ExecutionStatus,
)
from .learning import Forecast, ForecastKind
from .sqlite_support import SqliteLocation


class AttackSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AttackClass(str, Enum):
    AUTH = "AUTH"
    REPLAY = "REPLAY"
    DATA = "DATA"
    AUDIT = "AUDIT"
    LEARN = "LEARN"
    GOVERNANCE = "GOVERNANCE"


@dataclass(frozen=True)
class AdversarialFinding:
    attack_id: str
    severity: AttackSeverity
    attack_class: AttackClass
    passed: bool
    subject: str
    evidence: str
    remediation: str


@dataclass(frozen=True)
class AdversarialReport:
    findings: tuple[AdversarialFinding, ...]

    @property
    def passed(self) -> bool:
        return all(finding.passed for finding in self.findings)

    @property
    def critical_failures(self) -> int:
        return sum(
            1
            for finding in self.findings
            if not finding.passed and finding.severity is AttackSeverity.CRITICAL
        )

    @property
    def coverage(self) -> float:
        if not self.findings:
            return 1.0
        return sum(finding.passed for finding in self.findings) / len(self.findings)

    @property
    def classes(self) -> tuple[AttackClass, ...]:
        return tuple(sorted({finding.attack_class for finding in self.findings}, key=lambda item: item.value))


class AdversarialEngine:
    """Deterministic, bounded and fail-closed adversarial regression suite.

    Probes are read-only with respect to governance. Persistence probes use an
    isolated temporary database and deliberately tamper with test state so the
    real SINGULAR data store is never touched.
    """

    @staticmethod
    def _probe(
        attack_id: str,
        severity: AttackSeverity,
        attack_class: AttackClass,
        subject: str,
        operation: Callable[[], object],
        expected_exception: type[BaseException],
        remediation: str,
    ) -> AdversarialFinding:
        try:
            operation()
        except expected_exception as exc:
            return AdversarialFinding(
                attack_id, severity, attack_class, True, subject,
                f"Rejected: {type(exc).__name__}", remediation,
            )
        except Exception as exc:  # pragma: no cover - intentionally defensive
            return AdversarialFinding(
                attack_id, severity, attack_class, False, subject,
                f"Rejected for an unexpected reason: {type(exc).__name__}", remediation,
            )
        return AdversarialFinding(
            attack_id, severity, attack_class, False, subject,
            "Attack was not rejected.", remediation,
        )

    @classmethod
    def authority_suite(cls) -> AdversarialReport:
        findings = [
            cls._probe("AUTH-001", AttackSeverity.CRITICAL, AttackClass.AUTH, "COMMANDER -> AUTHORIZE", lambda: AuthorityProtocol.require("COMMANDER", AgentPower.AUTHORIZE), PermissionError, "Keep recommendation and authorization as separate authority domains."),
            cls._probe("AUTH-002", AttackSeverity.CRITICAL, AttackClass.AUTH, "RED_TEAM -> EXECUTE", lambda: AuthorityProtocol.require("RED_TEAM", AgentPower.EXECUTE), PermissionError, "A challenge must never become an execution override."),
            cls._probe("AUTH-003", AttackSeverity.CRITICAL, AttackClass.AUTH, "SYSTEM_ARCHITECT -> AUTHORIZE", lambda: AuthorityProtocol.require("SYSTEM_ARCHITECT", AgentPower.AUTHORIZE), PermissionError, "System changes must remain proposals until separately authorized."),
            cls._probe("AUTH-004", AttackSeverity.HIGH, AttackClass.AUTH, "UNKNOWN_AGENT -> EXECUTE", lambda: AuthorityProtocol.require("UNKNOWN", AgentPower.EXECUTE), ValueError, "Unknown identities must fail closed rather than inherit permissions."),
            cls._probe("AUTH-005", AttackSeverity.CRITICAL, AttackClass.AUTH, "COMMANDER -> SYSTEM_CHANGE", lambda: AuthorityProtocol.require("COMMANDER", AgentPower.SYSTEM_CHANGE), PermissionError, "No recommendation role may acquire system-change authority."),
            cls._probe("AUTH-006", AttackSeverity.CRITICAL, AttackClass.AUTH, "SYSTEM_ARCHITECT -> EXECUTE", lambda: AuthorityProtocol.require("SYSTEM_ARCHITECT", AgentPower.EXECUTE), PermissionError, "Architecture authority must never imply execution authority."),
            cls._probe("AUTH-007", AttackSeverity.MEDIUM, AttackClass.GOVERNANCE, "GOVERNOR -> HUMAN_FINAL", lambda: AuthorityProtocol.require("GOVERNOR", AgentPower.HUMAN_FINAL), PermissionError, "Governance may enforce policy but cannot impersonate final human authority."),
            cls._probe("AUTH-008", AttackSeverity.MEDIUM, AttackClass.GOVERNANCE, "GOVERNOR -> SYSTEM_CHANGE", lambda: AuthorityProtocol.require("GOVERNOR", AgentPower.SYSTEM_CHANGE), PermissionError, "Authorization authority must not imply authority to alter the system itself."),
        ]
        return AdversarialReport(tuple(findings))

    @classmethod
    def authentication_suite(cls) -> AdversarialReport:
        """Exercise credential, MFA, replay and persistence boundaries in isolation."""
        findings: list[AdversarialFinding] = []
        with tempfile.TemporaryDirectory(prefix="singular-auth-redteam-") as directory:
            db_path = Path(directory) / "auth.db"
            master_key = Fernet.generate_key()
            password = "Correct horse battery staple 2026!"

            auth = AuthenticationService(db_path, master_key=master_key, now=lambda: 1_000_000.0)
            user_id = auth.create_user("redteam", password)
            enrollment = auth.begin_totp_enrollment(user_id, password, now=1_000_020.0)

            def repr_probe() -> object:
                if enrollment.secret in repr(enrollment) or enrollment.otpauth_uri in repr(enrollment):
                    return None
                raise PermissionError("credential representation is redacted")

            findings.append(cls._probe(
                "AUTH-009", AttackSeverity.CRITICAL, AttackClass.AUTH,
                "TOTP enrollment secret leakage through repr",
                repr_probe,
                PermissionError,
                "Keep TOTP credentials out of repr and debug output.",
            ))

            def plaintext_totp_storage() -> object:
                with sqlite3.connect(db_path) as conn:
                    values = conn.execute("SELECT totp_ciphertext,pending_totp_ciphertext FROM auth_users WHERE user_id=?", (user_id,)).fetchone()
                if any(value is not None and enrollment.secret.encode("ascii") in bytes(value) for value in values):
                    return None
                raise PermissionError("TOTP secret is encrypted at rest")

            findings.append(cls._probe(
                "AUTH-010", AttackSeverity.CRITICAL, AttackClass.AUTH,
                "TOTP secret plaintext storage", plaintext_totp_storage, PermissionError,
                "Encrypt TOTP secrets at rest and never persist their plaintext representation.",
            ))

            def wrong_enrollment_code() -> object:
                for _ in range(5):
                    try:
                        auth.confirm_totp_enrollment(user_id, "000000", now=1_000_020.0)
                    except AuthenticationError:
                        continue
                return auth.confirm_totp_enrollment(user_id, _totp(enrollment.secret, 1_000_020.0), now=1_000_020.0)

            findings.append(cls._probe(
                "AUTH-011", AttackSeverity.HIGH, AttackClass.AUTH,
                "MFA enrollment brute-force after five failures", wrong_enrollment_code, RateLimited,
                "Persist MFA enrollment failures and fail closed at the configured threshold.",
            ))

            replay_db = Path(directory) / "replay.db"
            replay = AuthenticationService(replay_db, master_key=master_key, now=lambda: 2_000_000.0)
            replay_user = replay.create_user("replay", password)
            first = replay.begin_totp_enrollment(replay_user, password, now=2_000_000.0)
            recovery_codes = replay.confirm_totp_enrollment(replay_user, _totp(first.secret, 2_000_000.0), now=2_000_000.0)
            code = _totp(first.secret, 2_000_040.0)
            replay.authenticate("replay", password, otp=code, now=2_000_040.0)

            findings.append(cls._probe(
                "AUTH-012", AttackSeverity.CRITICAL, AttackClass.REPLAY,
                "TOTP replay in the same time step",
                lambda: replay.authenticate("replay", password, otp=code, now=2_000_040.0),
                AuthenticationError,
                "Atomically advance the durable TOTP counter before accepting a code.",
            ))

            recovery = recovery_codes[0]
            replay.authenticate("replay", password, recovery_code=recovery, now=2_000_100.0)
            findings.append(cls._probe(
                "AUTH-013", AttackSeverity.CRITICAL, AttackClass.REPLAY,
                "recovery-code replay",
                lambda: replay.authenticate("replay", password, recovery_code=recovery, now=2_000_100.0),
                AuthenticationError,
                "Recovery credentials must be single-use and atomically consumed.",
            ))

            rate_db = Path(directory) / "rate.db"
            rate = AuthenticationService(rate_db, master_key=master_key, now=lambda: 3_000_000.0)
            rate.create_user("rate", password)
            for _ in range(5):
                try:
                    rate.authenticate("rate", "wrong password 2026!", client_key="client-A", now=3_000_000.0)
                except AuthenticationError:
                    pass
            restarted = AuthenticationService(rate_db, master_key=master_key, now=lambda: 3_000_001.0)
            findings.append(cls._probe(
                "AUTH-014", AttackSeverity.HIGH, AttackClass.AUTH,
                "rate-limit bypass after process restart",
                lambda: restarted.authenticate("rate", password, client_key="client-A", now=3_000_001.0),
                RateLimited,
                "Keep authentication throttling state durable and keyed without storing raw client identifiers.",
            ))

            findings.append(cls._probe(
                "AUTH-015", AttackSeverity.CRITICAL, AttackClass.AUTH,
                "password-only MFA replacement",
                lambda: replay.begin_totp_enrollment(replay_user, password, now=2_000_130.0),
                SecondFactorRequired,
                "Changing an already configured second factor requires the existing second factor or a recovery credential.",
            ))
        return AdversarialReport(tuple(findings))

    @classmethod
    def persistence_suite(cls) -> AdversarialReport:
        findings: list[AdversarialFinding] = []
        with tempfile.TemporaryDirectory(prefix="singular-redteam-") as directory:
            db_path = Path(directory) / "redteam.db"
            store = DurableStore(db_path)
            audit = AuditTrail()
            first = audit.record("TEST", "RED_TEAM", "OK", {"case": "integrity"})
            second = audit.record("TEST", "RED_TEAM", "OK", {"case": "integrity-2"})
            store.record_audit(first)
            store.record_audit(second)

            def tamper_audit() -> object:
                with SqliteLocation(db_path).session() as conn:
                    conn.execute("UPDATE audit_events SET outcome='TAMPERED' WHERE event_id=?", (first.id,))
                return store.record_audit(audit.record("TEST", "RED_TEAM", "OK", {"case": "blocked"}))

            findings.append(cls._probe("AUDIT-001", AttackSeverity.CRITICAL, AttackClass.AUDIT, "tampered durable audit chain", tamper_audit, RuntimeError, "Refuse all new audit writes while the existing chain is compromised."))

            def gap_audit() -> object:
                fresh = DurableStore(Path(directory) / "gap.db")
                event = AuditEvent("TEST", "RED_TEAM", "OK", {"case": "gap"})
                forged = AuditEvent(event.event_type, event.actor, event.outcome, event.durable_payload(99, ""), event.timestamp, event.id)
                return fresh.record_audit(forged)

            findings.append(cls._probe("AUDIT-002", AttackSeverity.HIGH, AttackClass.AUDIT, "audit sequence jump", gap_audit, ValueError, "Require the next durable sequence to equal current length plus one."))

            def replay_different_result() -> object:
                bridge = ExecutionResultBridge()
                intent = ExecutionIntent("d1", "a1", "replay-key")
                bridge.record(intent, status=ExecutionStatus.SUCCEEDED, success=True, observed_value=10.0)
                return bridge.record(intent, status=ExecutionStatus.SUCCEEDED, success=True, observed_value=11.0)

            findings.append(cls._probe("REPLAY-001", AttackSeverity.CRITICAL, AttackClass.REPLAY, "idempotency key reused with different result", replay_different_result, RuntimeError, "Bind an idempotency key to exactly one deterministic result fingerprint."))

            forecast = Forecast("f-redteam", ForecastKind.BINARY, probability=0.9, confidence=0.9)
            result = ExecutionResult("d-redteam", forecast.id, "k-redteam", ExecutionStatus.SUCCEEDED, True, True)
            cycle = EconomicLearningEngine.evaluate(forecast, result)
            ledger = EconomicLearningLedger(store)
            ledger.record(cycle)

            def tamper_learning() -> object:
                with SqliteLocation(db_path).session() as conn:
                    conn.execute("UPDATE idempotency SET result=? WHERE key=?", ('{"forecast_id":"f-redteam","tampered":true}', ledger.key_for(cycle)))
                return ledger.get(forecast.id)

            findings.append(cls._probe("LEARN-001", AttackSeverity.CRITICAL, AttackClass.LEARN, "tampered economic learning record", tamper_learning, RuntimeError, "Verify durable learning fingerprints before restoring any cycle."))

            def tamper_learning_fingerprint() -> object:
                clean = DurableStore(Path(directory) / "fingerprint.db")
                clean_ledger = EconomicLearningLedger(clean)
                clean_ledger.record(cycle)
                with SqliteLocation(Path(directory) / "fingerprint.db").session() as conn:
                    conn.execute("UPDATE idempotency SET fingerprint=? WHERE key=?", (sha256(b"forged").hexdigest(), clean_ledger.key_for(cycle)))
                return clean_ledger.get(forecast.id)

            findings.append(cls._probe("DATA-001", AttackSeverity.CRITICAL, AttackClass.DATA, "forged learning fingerprint", tamper_learning_fingerprint, RuntimeError, "Treat a fingerprint mismatch as durable-data corruption and fail closed."))
        return AdversarialReport(tuple(findings))

    @classmethod
    def full_suite(cls) -> AdversarialReport:
        reports = (cls.authority_suite(), cls.authentication_suite(), cls.persistence_suite())
        findings = tuple(finding for report in reports for finding in report.findings)
        return AdversarialReport(findings)
