"""Durable, governed lifecycle for candidate learning improvements.

This registry separates learning evidence from activation. Candidates are immutable
proposals; evaluation is recorded explicitly; promotion requires an accepted human
review plus a measured regression-free comparison against the incumbent. Safety-
critical policy is never an eligible target of this registry.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from pathlib import Path

from .sqlite_support import SqliteLocation


class ImprovementKind(str, Enum):
    MODEL = "MODEL"
    STRATEGY = "STRATEGY"
    KNOWLEDGE = "KNOWLEDGE"
    MEMORY = "MEMORY"
    PARAMETERS = "PARAMETERS"


@dataclass(frozen=True)
class ImprovementCandidate:
    candidate_id: str
    kind: ImprovementKind
    target: str
    hypothesis: str
    evidence: str
    fingerprint: str
    safety_critical: bool = False

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.target.strip() or not self.hypothesis.strip():
            raise ValueError("improvement candidate identity and hypothesis are required")
        if not self.fingerprint.strip():
            raise ValueError("improvement candidate fingerprint is required")
        if self.safety_critical:
            raise PermissionError("safety-critical policy cannot be modified by the learning registry")


@dataclass(frozen=True)
class ImprovementEvaluation:
    candidate_id: str
    incumbent_version: str
    candidate_version: str
    incumbent_score: float
    candidate_score: float
    confidence: float
    regression: bool
    evaluated_at: str

    def __post_init__(self) -> None:
        for name, value in (("incumbent_score", self.incumbent_score), ("candidate_score", self.candidate_score), ("confidence", self.confidence)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.candidate_id.strip() or not self.incumbent_version.strip() or not self.candidate_version.strip():
            raise ValueError("evaluation identity fields are required")


@dataclass(frozen=True)
class ImprovementActivation:
    target: str
    version: str
    candidate_id: str
    activated_at: str


class ImprovementRegistry:
    """Persist candidates, evaluations and explicit activations with rollback."""

    def __init__(self, path: str | Path = "data/singular.db") -> None:
        self._location = SqliteLocation(path)
        self.path = self._location.reference
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return self._location.connect()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS improvement_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    safety_critical INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS improvement_evaluations (
                    candidate_id TEXT PRIMARY KEY,
                    incumbent_version TEXT NOT NULL,
                    candidate_version TEXT NOT NULL,
                    incumbent_score REAL NOT NULL,
                    candidate_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    regression INTEGER NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS improvement_reviews (
                    candidate_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS improvement_activations (
                    target TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    activated_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS improvement_activation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    version TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    activated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def candidate_fingerprint(*, kind: ImprovementKind, target: str, hypothesis: str, evidence: str) -> str:
        payload = {"kind": kind.value, "target": target, "hypothesis": hypothesis, "evidence": evidence}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def register(self, candidate: ImprovementCandidate) -> ImprovementCandidate:
        if candidate.safety_critical:
            raise PermissionError("safety-critical policy cannot enter the improvement lifecycle")
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM improvement_candidates WHERE candidate_id=?", (candidate.candidate_id,)).fetchone()
            if existing is not None:
                if existing["fingerprint"] != candidate.fingerprint:
                    raise ValueError("candidate id is already bound to different improvement content")
                return candidate
            conn.execute(
                "INSERT INTO improvement_candidates(candidate_id,kind,target,hypothesis,evidence,fingerprint,safety_critical,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (candidate.candidate_id, candidate.kind.value, candidate.target, candidate.hypothesis, candidate.evidence, candidate.fingerprint, int(candidate.safety_critical), now),
            )
        return candidate

    def evaluate(self, evaluation: ImprovementEvaluation) -> ImprovementEvaluation:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM improvement_candidates WHERE candidate_id=?", (evaluation.candidate_id,)).fetchone() is None:
                raise KeyError(evaluation.candidate_id)
            conn.execute(
                "INSERT OR REPLACE INTO improvement_evaluations(candidate_id,incumbent_version,candidate_version,incumbent_score,candidate_score,confidence,regression,evaluated_at) VALUES(?,?,?,?,?,?,?,?)",
                (evaluation.candidate_id, evaluation.incumbent_version, evaluation.candidate_version, evaluation.incumbent_score, evaluation.candidate_score, evaluation.confidence, int(evaluation.regression), evaluation.evaluated_at),
            )
        return evaluation

    def review(self, candidate_id: str, status: str) -> None:
        if status not in {"ACCEPTED", "REJECTED"}:
            raise ValueError("improvement review must be ACCEPTED or REJECTED")
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM improvement_candidates WHERE candidate_id=?", (candidate_id,)).fetchone() is None:
                raise KeyError(candidate_id)
            conn.execute("INSERT OR REPLACE INTO improvement_reviews(candidate_id,status,reviewed_at) VALUES(?,?,?)", (candidate_id, status, now))

    def promote(self, candidate_id: str) -> ImprovementActivation:
        with self._connect() as conn:
            candidate = conn.execute("SELECT target FROM improvement_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if candidate is None:
                raise KeyError(candidate_id)
            review = conn.execute("SELECT status FROM improvement_reviews WHERE candidate_id=?", (candidate_id,)).fetchone()
            if review is None or review["status"] != "ACCEPTED":
                raise PermissionError("improvement must have an ACCEPTED human review before promotion")
            evaluation = conn.execute("SELECT * FROM improvement_evaluations WHERE candidate_id=?", (candidate_id,)).fetchone()
            if evaluation is None:
                raise PermissionError("improvement must be evaluated before promotion")
            if evaluation["regression"] or evaluation["candidate_score"] <= evaluation["incumbent_score"] or evaluation["confidence"] < 0.8:
                raise PermissionError("improvement did not pass promotion gates")
            now = datetime.now(UTC).isoformat()
            activation = ImprovementActivation(candidate["target"], evaluation["candidate_version"], candidate_id, now)
            conn.execute("INSERT OR REPLACE INTO improvement_activations(target,version,candidate_id,activated_at) VALUES(?,?,?,?)", (activation.target, activation.version, activation.candidate_id, activation.activated_at))
            conn.execute("INSERT INTO improvement_activation_history(target,version,candidate_id,activated_at) VALUES(?,?,?,?)", (activation.target, activation.version, activation.candidate_id, activation.activated_at))
        return activation

    def rollback(self, target: str, *, version: str, candidate_id: str) -> ImprovementActivation:
        with self._connect() as conn:
            history = conn.execute(
                "SELECT 1 FROM improvement_activation_history WHERE target=? AND version=? AND candidate_id=? LIMIT 1",
                (target, version, candidate_id),
            ).fetchone()
            if history is None:
                raise PermissionError("rollback target must be a previously activated immutable version")
            now = datetime.now(UTC).isoformat()
            activation = ImprovementActivation(target, version, candidate_id, now)
            conn.execute("INSERT OR REPLACE INTO improvement_activations(target,version,candidate_id,activated_at) VALUES(?,?,?,?)", (target, version, candidate_id, now))
            conn.execute("INSERT INTO improvement_activation_history(target,version,candidate_id,activated_at) VALUES(?,?,?,?)", (target, version, candidate_id, now))
        return activation

    def active(self, target: str) -> ImprovementActivation | None:
        with self._connect() as conn:
            row = conn.execute("SELECT target,version,candidate_id,activated_at FROM improvement_activations WHERE target=?", (target,)).fetchone()
        return None if row is None else ImprovementActivation(row["target"], row["version"], row["candidate_id"], row["activated_at"])


__all__ = ["ImprovementKind", "ImprovementCandidate", "ImprovementEvaluation", "ImprovementActivation", "ImprovementRegistry"]
