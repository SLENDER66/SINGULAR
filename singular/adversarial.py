from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .authority import AgentPower, AuthorityProtocol


class AttackSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class AdversarialFinding:
    attack_id: str
    severity: AttackSeverity
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


class AdversarialEngine:
    """Deterministic fail-closed adversarial regression suite.

    A probe is considered safe only when the expected invariant is preserved.
    The engine reports failures; it never changes authority, policy or data.
    """

    @staticmethod
    def _probe(
        attack_id: str,
        severity: AttackSeverity,
        subject: str,
        operation: Callable[[], object],
        expected_exception: type[BaseException],
        remediation: str,
    ) -> AdversarialFinding:
        try:
            operation()
        except expected_exception as exc:
            return AdversarialFinding(
                attack_id, severity, True, subject, f"Rejected: {type(exc).__name__}", remediation
            )
        except Exception as exc:  # pragma: no cover - intentionally defensive
            return AdversarialFinding(
                attack_id,
                severity,
                False,
                subject,
                f"Rejected for an unexpected reason: {type(exc).__name__}",
                remediation,
            )
        return AdversarialFinding(
            attack_id,
            severity,
            False,
            subject,
            "Attack was not rejected.",
            remediation,
        )

    @classmethod
    def authority_suite(cls) -> AdversarialReport:
        findings = [
            cls._probe(
                "AUTH-001",
                AttackSeverity.CRITICAL,
                "COMMANDER -> AUTHORIZE",
                lambda: AuthorityProtocol.require("COMMANDER", AgentPower.AUTHORIZE),
                PermissionError,
                "Keep recommendation and authorization as separate authority domains.",
            ),
            cls._probe(
                "AUTH-002",
                AttackSeverity.CRITICAL,
                "RED_TEAM -> EXECUTE",
                lambda: AuthorityProtocol.require("RED_TEAM", AgentPower.EXECUTE),
                PermissionError,
                "A challenge must never become an execution override.",
            ),
            cls._probe(
                "AUTH-003",
                AttackSeverity.CRITICAL,
                "SYSTEM_ARCHITECT -> AUTHORIZE",
                lambda: AuthorityProtocol.require("SYSTEM_ARCHITECT", AgentPower.AUTHORIZE),
                PermissionError,
                "System changes must remain proposals until separately authorized.",
            ),
            cls._probe(
                "AUTH-004",
                AttackSeverity.HIGH,
                "UNKNOWN_AGENT -> POWER",
                lambda: AuthorityProtocol.require("UNKNOWN", AgentPower.EXECUTE),
                ValueError,
                "Unknown identities must fail closed rather than inherit permissions.",
            ),
        ]
        return AdversarialReport(tuple(findings))
