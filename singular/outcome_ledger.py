"""Durable outcome ledger closing the forecast -> result -> learning loop.

The ledger records what SINGULAR predicted, what actually happened and which
decision context produced the prediction. It proposes no authorization and never
mutates policy automatically.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from .decision_attestation import DecisionAttestationStore
from .durable import DurableStore
from .learning import CalibrationRecord, Forecast, ForecastKind, LearningEngine
from .sqlite_support import SqliteLocation
from .validated_trajectory_decision import ValidatedTrajectoryDecision


@dataclass(frozen=True)
class OutcomeObservation:
    record_id: str
    decision_id: str
    context_fingerprint: str
    execution_key: str
    forecast_id: str
    forecast_kind: ForecastKind
    forecast_confidence: float
    predicted_value: float
    actual_value: float
    absolute_error: float
    signed_error: float
    brier_score: float | None
    execution_status: str
    observed_at: str
    lesson: str
    previous_fingerprint: str
    fingerprint: str

    def __post_init__(self) -> None:
        # record() builds this from a payload holding forecast.kind.value, a
        # plain string, while _row() rehydrates the enum. Consumers compare with
        # `is`, so the freshly recorded observation silently failed every
        # ForecastKind check: a binary forecast was scored with the continuous
        # formula and never reached the Brier-based branch. Normalise here, at
        # the one type boundary both paths cross.
        if not isinstance(self.forecast_kind, ForecastKind):
            object.__setattr__(self, "forecast_kind", ForecastKind(self.forecast_kind))


class OutcomeLedger:
    """Append-only SQLite ledger for durable forecast calibration."""

    def __init__(self, path: str | Path = "data/singular.db", attestation_store: DecisionAttestationStore | None = None) -> None:
        self._location = SqliteLocation(path)
        self.path = self._location.reference
        self.attestation_store = attestation_store or DecisionAttestationStore(self.path)
        self._init_schema()

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return self._location.session()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outcome_ledger (
                    record_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    context_fingerprint TEXT NOT NULL,
                    execution_key TEXT NOT NULL,
                    forecast_id TEXT NOT NULL,
                    forecast_kind TEXT NOT NULL,
                    forecast_confidence REAL NOT NULL DEFAULT 0.0,
                    predicted_value REAL NOT NULL,
                    actual_value REAL NOT NULL,
                    absolute_error REAL NOT NULL,
                    signed_error REAL NOT NULL,
                    brier_score REAL,
                    execution_status TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    previous_fingerprint TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(outcome_ledger)")}
            if "forecast_confidence" not in columns:
                conn.execute("ALTER TABLE outcome_ledger ADD COLUMN forecast_confidence REAL NOT NULL DEFAULT 0.0")

    def _validate_execution_observation(
        self,
        decision: ValidatedTrajectoryDecision,
        execution_key: str,
        execution_status: str,
    ) -> None:
        """Require the learning observation to correspond to a real durable execution.

        This prevents a caller from poisoning calibration by supplying an arbitrary
        execution key or inventing a terminal status that never occurred. The
        durable execution row is the source of truth; the supplied values must match
        it exactly. Recovery-in-progress is deliberately not treated as an outcome.
        """
        mission_id = decision.contract.mission_id
        action_id = decision.global_report.action_id
        expected_key = DurableStore.idempotency_key("execute", mission_id, action_id)
        if execution_key != expected_key:
            raise PermissionError("La clé d'exécution ne correspond pas à l'identité durable de la décision.")

        execution = DurableStore(self.path).get_execution(execution_key)
        if execution is None:
            raise PermissionError("Aucune exécution durable correspondante n'existe pour cette observation.")
        if execution["mission_id"] != mission_id or execution["action_id"] != action_id:
            raise PermissionError("L'exécution observée n'est pas liée à la mission ou à l'action de la décision.")
        if execution["status"] != execution_status:
            raise ValueError("Le statut observé ne correspond pas au statut durable de l'exécution.")
        if execution_status not in {"COMPLETED", "FAILED"}:
            raise ValueError("Seules les exécutions terminales peuvent alimenter le ledger de résultats.")

    def record(
        self,
        *,
        decision: ValidatedTrajectoryDecision,
        forecast: Forecast,
        actual: bool | float,
        execution_key: str,
        execution_status: str,
        observed_at: str | None = None,
    ) -> OutcomeObservation:
        if not execution_key.strip() or not execution_status.strip():
            raise ValueError("execution key and status are required")
        if not decision.verify(now=decision.issued_at) or not self.attestation_store.verify_issuance(decision):
            raise PermissionError("only a durably issued, internally consistent decision can produce an outcome record")
        self._validate_execution_observation(decision, execution_key, execution_status)

        calibration: CalibrationRecord
        if forecast.kind is ForecastKind.BINARY:
            if not isinstance(actual, bool):
                raise TypeError("binary forecast outcomes must be bool")
            calibration = LearningEngine.evaluate_binary(forecast, actual)
            predicted = float(forecast.probability)
            observed = calibration.outcome
        else:
            if isinstance(actual, bool) or not isfinite(float(actual)):
                raise ValueError("numeric forecast outcomes must be finite numbers")
            observed = float(actual)
            calibration = LearningEngine.evaluate_numeric(forecast, observed)
            predicted = float(forecast.expected_value)

        timestamp = observed_at or datetime.now(UTC).isoformat()
        payload = {
            "decision_id": decision.decision_id,
            "context_fingerprint": decision.context_fingerprint,
            "execution_key": execution_key,
            "forecast_id": forecast.id,
            "forecast_kind": forecast.kind.value,
            "forecast_confidence": forecast.confidence,
            "predicted_value": predicted,
            "actual_value": observed,
            "absolute_error": calibration.error,
            "signed_error": observed - predicted,
            "brier_score": calibration.brier_score,
            "execution_status": execution_status,
            "observed_at": timestamp,
            "lesson": calibration.lesson,
        }
        semantic_id_payload = {
            "decision_id": payload["decision_id"],
            "execution_key": payload["execution_key"],
            "forecast_id": payload["forecast_id"],
        }
        record_id = hashlib.sha256(
            json.dumps(semantic_id_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]

        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM outcome_ledger WHERE record_id=?", (record_id,)).fetchone()
            if existing is not None:
                current = self._row(existing)
                comparable = {
                    "decision_id": current.decision_id,
                    "context_fingerprint": current.context_fingerprint,
                    "execution_key": current.execution_key,
                    "forecast_id": current.forecast_id,
                    "forecast_kind": current.forecast_kind.value,
                    "forecast_confidence": current.forecast_confidence,
                    "predicted_value": current.predicted_value,
                    "actual_value": current.actual_value,
                    "execution_status": current.execution_status,
                }
                incoming = {key: payload[key] for key in comparable}
                if comparable != incoming:
                    raise ValueError("outcome record already exists with different observed content")
                return current

            rows = conn.execute("SELECT fingerprint FROM outcome_ledger ORDER BY rowid").fetchall()
            previous = rows[-1]["fingerprint"] if rows else ""
            fingerprint_payload = {**payload, "record_id": record_id, "previous_fingerprint": previous}
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            conn.execute(
                "INSERT INTO outcome_ledger(record_id,decision_id,context_fingerprint,execution_key,forecast_id,forecast_kind,forecast_confidence,predicted_value,actual_value,absolute_error,signed_error,brier_score,execution_status,observed_at,lesson,previous_fingerprint,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record_id, payload["decision_id"], payload["context_fingerprint"], payload["execution_key"],
                    payload["forecast_id"], payload["forecast_kind"], payload["forecast_confidence"], payload["predicted_value"],
                    payload["actual_value"], payload["absolute_error"], payload["signed_error"], payload["brier_score"],
                    payload["execution_status"], payload["observed_at"], payload["lesson"], previous, fingerprint,
                ),
            )
            return OutcomeObservation(record_id=record_id, previous_fingerprint=previous, fingerprint=fingerprint, **payload)

    def list(self, *, decision_id: str | None = None) -> tuple[OutcomeObservation, ...]:
        query = "SELECT * FROM outcome_ledger"
        params: tuple[str, ...] = ()
        if decision_id is not None:
            query += " WHERE decision_id=?"
            params = (decision_id,)
        query += " ORDER BY rowid"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return tuple(self._row(row) for row in rows)

    def verify(self) -> bool:
        previous = ""
        try:
            for row in self.list():
                payload = {
                    "decision_id": row.decision_id,
                    "context_fingerprint": row.context_fingerprint,
                    "execution_key": row.execution_key,
                    "forecast_id": row.forecast_id,
                    "forecast_kind": row.forecast_kind.value,
                    "forecast_confidence": row.forecast_confidence,
                    "predicted_value": row.predicted_value,
                    "actual_value": row.actual_value,
                    "absolute_error": row.absolute_error,
                    "signed_error": row.signed_error,
                    "brier_score": row.brier_score,
                    "execution_status": row.execution_status,
                    "observed_at": row.observed_at,
                    "lesson": row.lesson,
                }
                expected_id = hashlib.sha256(
                    json.dumps(
                        {"decision_id": row.decision_id, "execution_key": row.execution_key, "forecast_id": row.forecast_id},
                        sort_keys=True, separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()[:24]
                if expected_id != row.record_id or row.previous_fingerprint != previous:
                    return False
                expected = hashlib.sha256(
                    json.dumps(
                        {**payload, "record_id": row.record_id, "previous_fingerprint": previous},
                        sort_keys=True, separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                if expected != row.fingerprint:
                    return False
                previous = row.fingerprint
        except (TypeError, ValueError, KeyError):
            return False
        return True

    @staticmethod
    def _row(row: sqlite3.Row) -> OutcomeObservation:
        return OutcomeObservation(
            record_id=row["record_id"],
            decision_id=row["decision_id"],
            context_fingerprint=row["context_fingerprint"],
            execution_key=row["execution_key"],
            forecast_id=row["forecast_id"],
            forecast_kind=ForecastKind(row["forecast_kind"]),
            forecast_confidence=float(row["forecast_confidence"]),
            predicted_value=float(row["predicted_value"]),
            actual_value=float(row["actual_value"]),
            absolute_error=float(row["absolute_error"]),
            signed_error=float(row["signed_error"]),
            brier_score=None if row["brier_score"] is None else float(row["brier_score"]),
            execution_status=row["execution_status"],
            observed_at=row["observed_at"],
            lesson=row["lesson"],
            previous_fingerprint=row["previous_fingerprint"],
            fingerprint=row["fingerprint"],
        )


__all__ = ["OutcomeObservation", "OutcomeLedger"]
