"""Durable queue for reviewable learning proposals.

Observed forecast errors can create learning proposals, but proposals remain
explicitly reviewable and cannot mutate execution policy or authorization by
themselves. A proposal may only be created from an outcome that is already
persisted and integrity-verified in the outcome ledger.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from .learning import CalibrationRecord, LearningEngine, LearningUpdate
from .outcome_ledger import OutcomeLedger, OutcomeObservation


@dataclass(frozen=True)
class LearningReview:
    review_id: str
    outcome_record_id: str
    forecast_id: str
    lesson: str
    hypothesis: str
    evidence_strength: float
    recommended_action: str
    status: str
    created_at: str
    reviewed_at: str | None = None

    def __post_init__(self) -> None:
        if not self.review_id.strip() or not self.outcome_record_id.strip() or not self.forecast_id.strip():
            raise ValueError("learning review identity fields are required")
        if self.status not in {"PENDING", "ACCEPTED", "REJECTED"}:
            raise ValueError("learning review status is invalid")
        if not isfinite(self.evidence_strength) or not 0.0 <= self.evidence_strength <= 1.0:
            raise ValueError("learning review evidence strength must be between 0 and 1")


class LearningReviewQueue:
    """Persist reviewable learning proposals without self-modifying execution rules."""

    def __init__(self, path: str | Path = "data/singular.db", *, outcome_ledger: OutcomeLedger | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.outcome_ledger = outcome_ledger or OutcomeLedger(self.path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_reviews (
                    review_id TEXT PRIMARY KEY,
                    outcome_record_id TEXT NOT NULL UNIQUE,
                    forecast_id TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    evidence_strength REAL NOT NULL,
                    recommended_action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT
                )
                """
            )

    def _verified_outcome(self, outcome: OutcomeObservation) -> OutcomeObservation:
        if not self.outcome_ledger.verify():
            raise PermissionError("outcome ledger integrity is invalid")
        persisted = next((item for item in self.outcome_ledger.list() if item.record_id == outcome.record_id), None)
        if persisted is None or persisted != outcome:
            raise PermissionError("learning proposal must reference the exact persisted outcome record")
        return persisted

    def propose(self, outcome: OutcomeObservation, *, repeated_pattern: bool = False) -> LearningReview:
        outcome = self._verified_outcome(outcome)
        calibration = CalibrationRecord(
            forecast_id=outcome.forecast_id,
            kind=outcome.forecast_kind,
            outcome=outcome.actual_value,
            error=outcome.absolute_error,
            brier_score=outcome.brier_score,
            forecast_confidence=outcome.forecast_confidence,
            lesson=outcome.lesson,
        )
        update: LearningUpdate = LearningEngine.propose_update(calibration, repeated_pattern=repeated_pattern)
        review_id = f"LR-{outcome.record_id}"
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM learning_reviews WHERE review_id=?", (review_id,)).fetchone()
            if existing is not None:
                return self._row(existing)
            conn.execute(
                "INSERT INTO learning_reviews(review_id,outcome_record_id,forecast_id,lesson,hypothesis,evidence_strength,recommended_action,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    review_id,
                    outcome.record_id,
                    outcome.forecast_id,
                    update.lesson,
                    update.hypothesis,
                    update.evidence_strength,
                    update.recommended_action,
                    "PENDING",
                    created_at,
                ),
            )
        return LearningReview(
            review_id,
            outcome.record_id,
            outcome.forecast_id,
            update.lesson,
            update.hypothesis,
            update.evidence_strength,
            update.recommended_action,
            "PENDING",
            created_at,
        )

    def review(self, review_id: str, status: str) -> LearningReview:
        if status not in {"ACCEPTED", "REJECTED"}:
            raise ValueError("review status must be ACCEPTED or REJECTED")
        reviewed_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE learning_reviews SET status=?, reviewed_at=? WHERE review_id=? AND status='PENDING'",
                (status, reviewed_at, review_id),
            )
            if cur.rowcount != 1:
                raise KeyError(review_id)
            row = conn.execute("SELECT * FROM learning_reviews WHERE review_id=?", (review_id,)).fetchone()
        return self._row(row)

    def pending(self) -> tuple[LearningReview, ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM learning_reviews WHERE status='PENDING' ORDER BY created_at, review_id").fetchall()
        return tuple(self._row(row) for row in rows)

    def _row(self, row: sqlite3.Row) -> LearningReview:
        return LearningReview(
            row["review_id"],
            row["outcome_record_id"],
            row["forecast_id"],
            row["lesson"],
            row["hypothesis"],
            float(row["evidence_strength"]),
            row["recommended_action"],
            row["status"],
            row["created_at"],
            row["reviewed_at"],
        )


__all__ = ["LearningReview", "LearningReviewQueue"]
