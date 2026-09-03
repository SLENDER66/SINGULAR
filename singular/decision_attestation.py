"""Durable issuance and revocation registry for validated trajectory decisions.

A ValidatedTrajectoryDecision is cryptographically self-consistent, but durability
still matters: after a process restart the execution boundary needs to know that
the exact decision was actually issued and has not been revoked. This module
stores only the attestation metadata, never executable callables.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from time import time

from .validated_trajectory_decision import ValidatedTrajectoryDecision


@dataclass(frozen=True)
class DecisionAttestation:
    decision_id: str
    context_fingerprint: str
    issued_at: float
    expires_at: float
    status: str
    issuer: str
    created_at: str
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.context_fingerprint.strip() or not self.issuer.strip():
            raise ValueError("decision attestation identity fields are required")
        if self.status not in {"ISSUED", "REVOKED"}:
            raise ValueError("decision attestation status is invalid")
        if not isfinite(self.issued_at) or not isfinite(self.expires_at) or self.expires_at <= self.issued_at:
            raise ValueError("decision attestation validity interval is invalid")


class DecisionAttestationStore:
    """SQLite-backed, fail-closed attestation registry."""

    def __init__(self, path: str | Path = "data/singular.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_attestations (
                    decision_id TEXT PRIMARY KEY,
                    context_fingerprint TEXT NOT NULL,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )

    def issue(self, decision: ValidatedTrajectoryDecision, *, issuer: str = "singular") -> DecisionAttestation:
        if not isinstance(decision, ValidatedTrajectoryDecision) or not decision.verify():
            raise ValueError("only a valid active decision can be attested")
        if not issuer.strip():
            raise ValueError("issuer is required")
        now = time()
        if now < decision.issued_at or now >= decision.expires_at:
            raise ValueError("cannot attest an inactive decision")
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT decision_id,context_fingerprint,issued_at,expires_at,status,issuer,created_at,revoked_at "
                "FROM decision_attestations WHERE decision_id=?",
                (decision.decision_id,),
            ).fetchone()
            if existing is not None:
                current = self._row(existing)
                if current.context_fingerprint != decision.context_fingerprint:
                    raise ValueError("decision id is already bound to a different context fingerprint")
                if current.status == "REVOKED":
                    raise PermissionError("revoked decision ids cannot be re-issued")
                return current
            conn.execute(
                "INSERT INTO decision_attestations(decision_id,context_fingerprint,issued_at,expires_at,status,issuer,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (decision.decision_id, decision.context_fingerprint, decision.issued_at, decision.expires_at, "ISSUED", issuer, created_at),
            )
        return DecisionAttestation(
            decision.decision_id, decision.context_fingerprint, decision.issued_at, decision.expires_at,
            "ISSUED", issuer, created_at,
        )

    def get(self, decision_id: str) -> DecisionAttestation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT decision_id,context_fingerprint,issued_at,expires_at,status,issuer,created_at,revoked_at "
                "FROM decision_attestations WHERE decision_id=?",
                (decision_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def verify(self, decision: ValidatedTrajectoryDecision, *, now: float | None = None) -> bool:
        if not isinstance(decision, ValidatedTrajectoryDecision):
            return False
        current_time = time() if now is None else now
        if not isfinite(current_time) or not decision.verify(now=current_time):
            return False
        attestation = self.get(decision.decision_id)
        if attestation is None or attestation.status != "ISSUED":
            return False
        if attestation.context_fingerprint != decision.context_fingerprint:
            return False
        return attestation.issued_at == decision.issued_at and attestation.expires_at == decision.expires_at

    def revoke(self, decision_id: str) -> DecisionAttestation:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE decision_attestations SET status='REVOKED', revoked_at=? WHERE decision_id=? AND status='ISSUED'",
                (now, decision_id),
            )
            if cur.rowcount != 1:
                raise KeyError(decision_id)
            row = conn.execute(
                "SELECT decision_id,context_fingerprint,issued_at,expires_at,status,issuer,created_at,revoked_at "
                "FROM decision_attestations WHERE decision_id=?",
                (decision_id,),
            ).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> DecisionAttestation:
        return DecisionAttestation(
            row["decision_id"], row["context_fingerprint"], float(row["issued_at"]), float(row["expires_at"]),
            row["status"], row["issuer"], row["created_at"], row["revoked_at"],
        )


class ValidatedDecisionIssuer:
    """Issues decisions only after full validation and records durable attestation."""

    def __init__(self, store: DecisionAttestationStore, *, issuer: str = "singular") -> None:
        if not issuer.strip():
            raise ValueError("issuer is required")
        self.store = store
        self.issuer = issuer

    def issue(self, decision: ValidatedTrajectoryDecision) -> DecisionAttestation:
        return self.store.issue(decision, issuer=self.issuer)

    def verify(self, decision: ValidatedTrajectoryDecision, *, now: float | None = None) -> bool:
        return self.store.verify(decision, now=now)


__all__ = ["DecisionAttestation", "DecisionAttestationStore", "ValidatedDecisionIssuer"]
