from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .consistency import ConsistencyViolation, CrossDomainConsistencyChecker


@dataclass(frozen=True)
class CoherenceReport:
    """Read-only gate describing whether the durable state is coherent enough to proceed."""

    coherent: bool
    violations: tuple[ConsistencyViolation, ...]
    blockers: tuple[str, ...]


class GlobalCoherenceGuard:
    """Fail closed when durable cross-domain state contradicts itself.

    This guard deliberately does not execute, repair, or mutate anything. It is
    a precondition layer: callers can inspect the report before planning or
    execution, while the existing governance and human-approval controls remain
    authoritative for permissions and irreversible actions.
    """

    def __init__(self, checker: CrossDomainConsistencyChecker) -> None:
        self.checker = checker

    def inspect(self, mission_id: str | None = None) -> CoherenceReport:
        violations = self.checker.check(mission_id)
        blockers = tuple(dict.fromkeys(v.code for v in violations))
        return CoherenceReport(
            coherent=not violations,
            violations=violations,
            blockers=blockers,
        )

    def require_coherent(self, mission_id: str | None = None) -> CoherenceReport:
        report = self.inspect(mission_id)
        if not report.coherent:
            raise RuntimeError(
                "État global incohérent : " + ", ".join(report.blockers)
            )
        return report

    @staticmethod
    def summarize(violations: Iterable[ConsistencyViolation]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(v.code for v in violations))
