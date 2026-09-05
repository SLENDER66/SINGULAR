"""Durable, governed lifecycle for candidate learning improvements.

This registry separates learning evidence from activation. Candidates are
immutable proposals; evaluation is recorded explicitly and cannot be rewritten
afterwards; promotion requires a human review that is bound to the exact
evaluation it read, plus a measured regression-free comparison against the
incumbent. Safety-critical policy is never an eligible target.

The chain that has to hold end to end is:

    candidate -> artifact -> artifact fingerprint -> evaluation -> approval
    -> activation

A version string is a label, not an identity. Without an artifact fingerprint
running through every step, a system can register candidate X, evaluate
"v42", and activate something else entirely under the same name -- the
evaluation would attest to an artifact nobody ever ran. Every stage therefore
carries the artifact fingerprint and refuses to proceed when it does not match
the one registered with the candidate.

Safety-critical policy is out of scope for this lifecycle, and which targets
are safety-critical is decided here from the target itself. It used to be a
`safety_critical` flag carried by the candidate: a proposal declaring itself
harmless was believed, so a candidate targeting the execution boundary simply
left the flag false and entered the lifecycle unchallenged. A proposal is
never a witness about its own blast radius.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import AbstractContextManager
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from pathlib import Path

from .sqlite_support import SqliteLocation

#: Bumped whenever the persisted shape changes. `CREATE TABLE IF NOT EXISTS`
#: silently tolerates a database written by a different version of this module,
#: which is how a registry ends up reading columns that mean something else.
SCHEMA_VERSION = 2


class ImprovementKind(str, Enum):
    MODEL = "MODEL"
    STRATEGY = "STRATEGY"
    KNOWLEDGE = "KNOWLEDGE"
    MEMORY = "MEMORY"
    PARAMETERS = "PARAMETERS"


#: Target namespaces this lifecycle may never touch, whatever a caller declares.
#: These name the surfaces the mandate keeps outside learning: the execution
#: boundary, authorization, identity, integrity and the evidence about them.
SAFETY_CRITICAL_NAMESPACES: frozenset[str] = frozenset(
    {
        "approval", "attestation", "audit", "authentication", "authority", "authorization",
        "boundary", "capability", "constitution", "durable", "effect", "execution",
        "governance", "governor", "identity", "integrity", "invariant", "lease", "policy",
        "provenance", "recovery", "red_team", "redteam", "safety", "security", "values",
    }
)

#: Namespaces a candidate may target by default. An allowlist rather than a
#: denylist: with a denylist alone, every target name invented after this list
#: was written would be adaptive by default, so forgetting to extend it would
#: fail open on exactly the surface that matters.
DEFAULT_ADAPTIVE_NAMESPACES: frozenset[str] = frozenset(
    {"domain", "economic", "forecast", "knowledge", "memory", "model", "parameters", "strategy", "world_model"}
)


def target_namespace(target: str) -> str:
    """The leading dotted segment of a target, normalized for comparison."""
    return target.strip().lower().split(".", 1)[0].strip()


def artifact_fingerprint(artifact: object) -> str:
    """A stable identity for the thing that would actually run."""
    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ImprovementCandidate:
    candidate_id: str
    kind: ImprovementKind
    target: str
    hypothesis: str
    evidence: str
    artifact_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.target.strip() or not self.hypothesis.strip():
            raise ValueError("improvement candidate identity and hypothesis are required")
        if not self.fingerprint.strip():
            raise ValueError("improvement candidate fingerprint is required")
        if not self.artifact_fingerprint.strip():
            raise ValueError("improvement candidate artifact fingerprint is required")


@dataclass(frozen=True)
class ImprovementEvaluation:
    candidate_id: str
    artifact_fingerprint: str
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
        if not self.artifact_fingerprint.strip():
            raise ValueError("an evaluation must name the artifact it evaluated")

    @property
    def fingerprint(self) -> str:
        """Identity of this evaluation's content, so a review can be bound to it."""
        payload = {
            "candidate_id": self.candidate_id,
            "artifact_fingerprint": self.artifact_fingerprint,
            "incumbent_version": self.incumbent_version,
            "candidate_version": self.candidate_version,
            "incumbent_score": self.incumbent_score,
            "candidate_score": self.candidate_score,
            "confidence": self.confidence,
            "regression": self.regression,
            "evaluated_at": self.evaluated_at,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ImprovementActivation:
    target: str
    version: str
    candidate_id: str
    artifact_fingerprint: str
    activated_at: str


class ImprovementRegistry:
    """Persist candidates, evaluations and explicit activations with rollback."""

    def __init__(self, path: str | Path = "data/singular.db", *, adaptive_namespaces: Iterable[str] | None = None) -> None:
        self._location = SqliteLocation(path)
        self.path = self._location.reference
        declared = DEFAULT_ADAPTIVE_NAMESPACES if adaptive_namespaces is None else adaptive_namespaces
        self.adaptive_namespaces = frozenset(namespace.strip().lower() for namespace in declared)
        # The deployment may narrow or extend the adaptive perimeter, but it can
        # never declare a safety-critical namespace adaptive: that would move the
        # decision back to whoever wants the change made.
        overlap = sorted(self.adaptive_namespaces & SAFETY_CRITICAL_NAMESPACES)
        if overlap:
            raise PermissionError(f"safety-critical namespaces cannot be declared adaptive: {', '.join(overlap)}")
        self._init_schema()

    def _assert_target_is_adaptive(self, target: str) -> None:
        """Classify a target from its own name, never from what a candidate claims.

        Checked again at activation rather than only at registration: a
        perimeter that tightens between the two, or a row inserted straight into
        the database, would otherwise activate against a target this registry
        would refuse to register today.
        """
        namespace = target_namespace(target)
        if namespace in SAFETY_CRITICAL_NAMESPACES:
            raise PermissionError(f"safety-critical target '{target}' cannot enter the improvement lifecycle")
        if namespace not in self.adaptive_namespaces:
            raise PermissionError(f"target '{target}' is outside the declared adaptive perimeter")

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return self._location.session(foreign_keys=True)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS improvement_schema (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM improvement_schema").fetchone()
            if row is None:
                self._assert_no_legacy_data(conn)
                conn.execute("INSERT INTO improvement_schema(version) VALUES(?)", (SCHEMA_VERSION,))
            else:
                version = int(row["version"])
                if version > SCHEMA_VERSION:
                    raise RuntimeError(
                        f"improvement registry schema v{version} was written by a newer version of SINGULAR; refusing to read it"
                    )
                if version < SCHEMA_VERSION:
                    raise RuntimeError(
                        f"improvement registry schema v{version} predates v{SCHEMA_VERSION} and has no automatic migration"
                    )
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS improvement_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    artifact_fingerprint TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    safety_critical INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS improvement_evaluations (
                    candidate_id TEXT PRIMARY KEY,
                    artifact_fingerprint TEXT NOT NULL,
                    incumbent_version TEXT NOT NULL,
                    candidate_version TEXT NOT NULL,
                    incumbent_score REAL NOT NULL,
                    candidate_score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    regression INTEGER NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    evaluation_fingerprint TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS improvement_reviews (
                    candidate_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    evaluation_fingerprint TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS improvement_activations (
                    target TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    artifact_fingerprint TEXT NOT NULL,
                    activated_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES improvement_candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS improvement_activation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    version TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    artifact_fingerprint TEXT NOT NULL,
                    activated_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _assert_no_legacy_data(conn: sqlite3.Connection) -> None:
        """A pre-versioning database cannot be upgraded silently.

        The v1 tables carry no artifact identity, so there is nothing to migrate
        an existing candidate's artifact fingerprint from. Inventing one would
        assert an evaluation covered an artifact nobody can name.
        """
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='improvement_candidates'"
        ).fetchone()
        if existing is None:
            return
        columns = {row[1] for row in conn.execute("PRAGMA table_info(improvement_candidates)")}
        if "artifact_fingerprint" in columns:
            return
        rows = conn.execute("SELECT COUNT(*) AS total FROM improvement_candidates").fetchone()
        if rows is not None and int(rows["total"]) > 0:
            raise RuntimeError(
                "improvement registry holds unversioned candidates with no artifact identity; "
                "migrate them explicitly before opening this database"
            )
        conn.executescript(
            """
            DROP TABLE IF EXISTS improvement_activation_history;
            DROP TABLE IF EXISTS improvement_activations;
            DROP TABLE IF EXISTS improvement_reviews;
            DROP TABLE IF EXISTS improvement_evaluations;
            DROP TABLE IF EXISTS improvement_candidates;
            """
        )

    @staticmethod
    def candidate_fingerprint(*, kind: ImprovementKind, target: str, hypothesis: str, evidence: str, artifact_fingerprint: str) -> str:
        payload = {
            "kind": kind.value,
            "target": target,
            "hypothesis": hypothesis,
            "evidence": evidence,
            "artifact_fingerprint": artifact_fingerprint,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def register(self, candidate: ImprovementCandidate) -> ImprovementCandidate:
        self._assert_target_is_adaptive(candidate.target)
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM improvement_candidates WHERE candidate_id=?", (candidate.candidate_id,)).fetchone()
            if existing is not None:
                if existing["fingerprint"] != candidate.fingerprint:
                    raise ValueError("candidate id is already bound to different improvement content")
                if existing["artifact_fingerprint"] != candidate.artifact_fingerprint:
                    raise ValueError("candidate id is already bound to a different artifact")
                return candidate
            conn.execute(
                "INSERT INTO improvement_candidates(candidate_id,kind,target,hypothesis,evidence,artifact_fingerprint,fingerprint,safety_critical,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                # safety_critical is derived, not declared: _assert_target_is_adaptive
                # has already refused every target that would store a 1 here.
                (candidate.candidate_id, candidate.kind.value, candidate.target, candidate.hypothesis, candidate.evidence,
                 candidate.artifact_fingerprint, candidate.fingerprint, 0, now),
            )
        return candidate

    def evaluate(self, evaluation: ImprovementEvaluation) -> ImprovementEvaluation:
        """Record one evaluation, bound to the candidate's registered artifact.

        Write-once. The previous implementation used INSERT OR REPLACE, so an
        evaluation stayed mutable after a human had reviewed it: register,
        obtain an ACCEPTED review, then overwrite the evaluation with favourable
        numbers and promote. The review attested to something that no longer
        existed.
        """
        with self._connect() as conn:
            candidate = conn.execute(
                "SELECT artifact_fingerprint FROM improvement_candidates WHERE candidate_id=?", (evaluation.candidate_id,)
            ).fetchone()
            if candidate is None:
                raise KeyError(evaluation.candidate_id)
            if candidate["artifact_fingerprint"] != evaluation.artifact_fingerprint:
                raise PermissionError("evaluation does not cover the artifact registered for this candidate")
            existing = conn.execute(
                "SELECT evaluation_fingerprint FROM improvement_evaluations WHERE candidate_id=?", (evaluation.candidate_id,)
            ).fetchone()
            if existing is not None:
                if existing["evaluation_fingerprint"] != evaluation.fingerprint:
                    raise PermissionError("an improvement evaluation is immutable once recorded")
                return evaluation
            conn.execute(
                "INSERT INTO improvement_evaluations(candidate_id,artifact_fingerprint,incumbent_version,candidate_version,"
                "incumbent_score,candidate_score,confidence,regression,evaluated_at,evaluation_fingerprint)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (evaluation.candidate_id, evaluation.artifact_fingerprint, evaluation.incumbent_version, evaluation.candidate_version,
                 evaluation.incumbent_score, evaluation.candidate_score, evaluation.confidence, int(evaluation.regression),
                 evaluation.evaluated_at, evaluation.fingerprint),
            )
        return evaluation

    def review(self, candidate_id: str, status: str) -> None:
        """Record a human decision, bound to the evaluation it read.

        A review with nothing to review is not a review, so an evaluation must
        exist first -- which is also the order the lifecycle describes:
        candidate, evaluation, review, promotion, activation.
        """
        if status not in {"ACCEPTED", "REJECTED"}:
            raise ValueError("improvement review must be ACCEPTED or REJECTED")
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM improvement_candidates WHERE candidate_id=?", (candidate_id,)).fetchone() is None:
                raise KeyError(candidate_id)
            evaluation = conn.execute(
                "SELECT evaluation_fingerprint FROM improvement_evaluations WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if evaluation is None:
                raise PermissionError("an improvement must be evaluated before it can be reviewed")
            existing = conn.execute("SELECT status FROM improvement_reviews WHERE candidate_id=?", (candidate_id,)).fetchone()
            if existing is not None:
                if existing["status"] != status:
                    raise PermissionError("an improvement review is final and cannot be changed")
                return
            conn.execute(
                "INSERT INTO improvement_reviews(candidate_id,status,evaluation_fingerprint,reviewed_at) VALUES(?,?,?,?)",
                (candidate_id, status, evaluation["evaluation_fingerprint"], now),
            )

    def promote(self, candidate_id: str) -> ImprovementActivation:
        with self._connect() as conn:
            candidate = conn.execute(
                "SELECT target,artifact_fingerprint FROM improvement_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if candidate is None:
                raise KeyError(candidate_id)
            review = conn.execute(
                "SELECT status,evaluation_fingerprint FROM improvement_reviews WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if review is None or review["status"] != "ACCEPTED":
                raise PermissionError("improvement must have an ACCEPTED human review before promotion")
            row = conn.execute("SELECT * FROM improvement_evaluations WHERE candidate_id=?", (candidate_id,)).fetchone()
            if row is None:
                raise PermissionError("improvement must be evaluated before promotion")
            # Recompute from the stored fields rather than trusting the stored
            # fingerprint. Comparing the two stored values only proves they were
            # written together: anyone editing the row directly would leave the
            # fingerprint alone and the review would still appear to cover it.
            evaluation = self._evaluation_from_row(row)
            if evaluation.fingerprint != row["evaluation_fingerprint"]:
                raise PermissionError("the recorded evaluation does not match its own fingerprint")
            if evaluation.fingerprint != review["evaluation_fingerprint"]:
                raise PermissionError("the reviewed evaluation is not the evaluation on record")
            if evaluation.artifact_fingerprint != candidate["artifact_fingerprint"]:
                raise PermissionError("the evaluated artifact is not the artifact registered for this candidate")
            if evaluation.regression or evaluation.candidate_score <= evaluation.incumbent_score or evaluation.confidence < 0.8:
                raise PermissionError("improvement did not pass promotion gates")
            now = datetime.now(UTC).isoformat()
            activation = ImprovementActivation(
                candidate["target"], evaluation.candidate_version, candidate_id, candidate["artifact_fingerprint"], now
            )
            self._activate(conn, activation)
        return activation

    @staticmethod
    def _evaluation_from_row(row: sqlite3.Row) -> ImprovementEvaluation:
        return ImprovementEvaluation(
            candidate_id=row["candidate_id"],
            artifact_fingerprint=row["artifact_fingerprint"],
            incumbent_version=row["incumbent_version"],
            candidate_version=row["candidate_version"],
            incumbent_score=float(row["incumbent_score"]),
            candidate_score=float(row["candidate_score"]),
            confidence=float(row["confidence"]),
            regression=bool(row["regression"]),
            evaluated_at=row["evaluated_at"],
        )

    def evaluation_of(self, candidate_id: str) -> ImprovementEvaluation | None:
        """The recorded evaluation, refusing one whose row no longer matches it."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM improvement_evaluations WHERE candidate_id=?", (candidate_id,)).fetchone()
        if row is None:
            return None
        evaluation = self._evaluation_from_row(row)
        if evaluation.fingerprint != row["evaluation_fingerprint"]:
            raise PermissionError("the recorded evaluation does not match its own fingerprint")
        return evaluation

    def rollback(self, target: str, *, version: str, candidate_id: str, artifact_fingerprint: str) -> ImprovementActivation:
        """Restore a version that was really activated, as the artifact it was.

        The version alone is not enough: two activations could share a label
        while running different artifacts, and rolling back to a label would
        then activate whichever one the caller named.
        """
        with self._connect() as conn:
            history = conn.execute(
                "SELECT 1 FROM improvement_activation_history WHERE target=? AND version=? AND candidate_id=? AND artifact_fingerprint=? LIMIT 1",
                (target, version, candidate_id, artifact_fingerprint),
            ).fetchone()
            if history is None:
                raise PermissionError("rollback target must be a previously activated immutable version")
            activation = ImprovementActivation(target, version, candidate_id, artifact_fingerprint, datetime.now(UTC).isoformat())
            self._activate(conn, activation)
        return activation

    def _activate(self, conn: sqlite3.Connection, activation: ImprovementActivation) -> None:
        self._assert_target_is_adaptive(activation.target)
        conn.execute(
            "INSERT OR REPLACE INTO improvement_activations(target,version,candidate_id,artifact_fingerprint,activated_at) VALUES(?,?,?,?,?)",
            (activation.target, activation.version, activation.candidate_id, activation.artifact_fingerprint, activation.activated_at),
        )
        conn.execute(
            "INSERT INTO improvement_activation_history(target,version,candidate_id,artifact_fingerprint,activated_at) VALUES(?,?,?,?,?)",
            (activation.target, activation.version, activation.candidate_id, activation.artifact_fingerprint, activation.activated_at),
        )

    def active(self, target: str) -> ImprovementActivation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT target,version,candidate_id,artifact_fingerprint,activated_at FROM improvement_activations WHERE target=?",
                (target,),
            ).fetchone()
        if row is None:
            return None
        return ImprovementActivation(row["target"], row["version"], row["candidate_id"], row["artifact_fingerprint"], row["activated_at"])


__all__ = [
    "DEFAULT_ADAPTIVE_NAMESPACES",
    "SAFETY_CRITICAL_NAMESPACES",
    "SCHEMA_VERSION",
    "ImprovementActivation",
    "ImprovementCandidate",
    "ImprovementEvaluation",
    "ImprovementKind",
    "ImprovementRegistry",
    "artifact_fingerprint",
    "target_namespace",
]
