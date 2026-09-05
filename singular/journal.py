"""A decision journal that refuses to let activity pass for results.

The constitution this repository is built to satisfy opens with one sentence:
"Maximiser le progrès réel de Thomas sous contraintes, sans confondre activité
et résultat." Nothing in the codebase enforced it. Thirteen thousand lines were
written across four versions, each predicted to move the project forward, and
none of those predictions was ever written down or checked.

This is the smallest thing that fixes that. Before doing something, you record
what you expect and how sure you are. When the horizon passes, the entry comes
back and asks what actually happened. It then tells you where your confidence is
wrong and where your hours went.

It deliberately does not use the execution boundary. That machinery governs
actions on the world and is heavy on purpose; a journal entry changes nothing
outside your own head. What it does borrow is the discipline: entries are
hash-chained, so a prediction cannot be quietly improved after the outcome is
known. A journal you can edit afterwards teaches you nothing.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import AbstractContextManager
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from math import isfinite
from pathlib import Path

from .learning import Forecast, ForecastKind, LearningEngine
from .sqlite_support import SqliteLocation

SCHEMA_VERSION = 1
DEFAULT_PATH = Path.home() / ".singular" / "journal.db"


class Tier(str, Enum):
    """The constitution's hierarchy, in its own order.

    Recording which rung a decision serves is the whole point: it is how you
    find out you spent a month on Patrimoine while Revenus stayed empty.
    """

    STABILITE = "STABILITE"
    REVENUS = "REVENUS"
    CAPACITES = "CAPACITES"
    OPPORTUNITES = "OPPORTUNITES"
    PATRIMOINE = "PATRIMOINE"
    LIBERTE = "LIBERTE"

    @property
    def rank(self) -> int:
        return list(Tier).index(self) + 1


class Status(str, Enum):
    OPEN = "OPEN"
    HAPPENED = "HAPPENED"
    DID_NOT_HAPPEN = "DID_NOT_HAPPEN"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True)
class Entry:
    entry_id: str
    title: str
    action: str
    predicted: str
    probability: float
    tier: Tier
    cost_hours: float
    horizon_days: int
    created_at: str
    due_at: str
    status: Status
    resolved_at: str | None
    lesson: str | None
    brier_score: float | None
    previous_fingerprint: str
    fingerprint: str

    @property
    def is_open(self) -> bool:
        return self.status is Status.OPEN

    def overdue_days(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        return max(0, (moment - datetime.fromisoformat(self.due_at)).days)


def _fingerprint(payload: dict, previous: str) -> str:
    material = json.dumps({"previous": previous, **payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class DecisionJournal:
    """Append-only, hash-chained record of what you expected and what happened."""

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self._location = SqliteLocation(path)
        self.path = self._location.reference
        self._init_schema()

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return self._location.session()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS journal_schema (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM journal_schema").fetchone()
            if row is None:
                conn.execute("INSERT INTO journal_schema(version) VALUES(?)", (SCHEMA_VERSION,))
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError(f"journal schema v{int(row['version'])} does not match v{SCHEMA_VERSION}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    predicted TEXT NOT NULL,
                    probability REAL NOT NULL,
                    tier TEXT NOT NULL,
                    cost_hours REAL NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolved_at TEXT,
                    lesson TEXT,
                    brier_score REAL,
                    previous_fingerprint TEXT NOT NULL,
                    fingerprint TEXT NOT NULL
                )
                """
            )

    # --- writing -------------------------------------------------------------

    def add(
        self,
        *,
        title: str,
        action: str,
        predicted: str,
        probability: float,
        tier: Tier,
        cost_hours: float,
        horizon_days: int,
        now: datetime | None = None,
    ) -> Entry:
        """Record a decision before acting on it.

        The probability is not decoration. It is what makes the entry checkable:
        "I think this works" cannot be wrong, "70% this produces a reply within
        14 days" can.
        """
        for name, value in (("probability", probability), ("cost_hours", cost_hours)):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 < probability < 1:
            raise ValueError("probability must be strictly between 0 and 1: certainty is not a forecast")
        if cost_hours < 0:
            raise ValueError("cost_hours cannot be negative")
        if horizon_days < 1:
            raise ValueError("a decision needs a horizon of at least one day to be checkable")
        if not title.strip() or not action.strip() or not predicted.strip():
            raise ValueError("title, action and predicted outcome are all required")

        moment = now or datetime.now(UTC)
        entry_id = "DEC-" + uuid.uuid4().hex[:8]
        payload = {
            "entry_id": entry_id, "title": title, "action": action, "predicted": predicted,
            "probability": probability, "tier": tier.value, "cost_hours": cost_hours,
            "horizon_days": horizon_days, "created_at": moment.isoformat(),
        }
        with self._connect() as conn:
            # Same reason as the outcome ledger and the audit trail: reading the
            # head and inserting behind it has to be one serialised step, or two
            # writers link to the same entry and verify() reports a journal
            # nobody touched as broken -- for good, since entries are never
            # rewritten.
            conn.execute("BEGIN IMMEDIATE")
            previous = self._head(conn)
            fingerprint = _fingerprint(payload, previous)
            due = (moment + timedelta(days=horizon_days)).isoformat()
            conn.execute(
                "INSERT INTO journal_entries(entry_id,title,action,predicted,probability,tier,cost_hours,horizon_days,"
                "created_at,due_at,status,resolved_at,lesson,brier_score,previous_fingerprint,fingerprint)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry_id, title, action, predicted, probability, tier.value, cost_hours, horizon_days,
                 moment.isoformat(), due, Status.OPEN.value, None, None, None, previous, fingerprint),
            )
        return Entry(entry_id, title, action, predicted, probability, tier, cost_hours, horizon_days,
                     moment.isoformat(), due, Status.OPEN, None, None, None, previous, fingerprint)

    def resolve(self, entry_id: str, *, happened: bool, lesson: str = "", now: datetime | None = None) -> Entry:
        """Record what actually happened. Scores the prediction, does not rewrite it."""
        moment = now or datetime.now(UTC)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
            if row is None:
                raise KeyError(entry_id)
            if row["status"] != Status.OPEN.value:
                raise PermissionError(f"{entry_id} was already resolved as {row['status']}; history is not editable")
            record = LearningEngine.evaluate_binary(
                Forecast(entry_id, ForecastKind.BINARY, probability=row["probability"], confidence=row["probability"]),
                happened,
            )
            status = Status.HAPPENED if happened else Status.DID_NOT_HAPPEN
            conn.execute(
                "UPDATE journal_entries SET status=?, resolved_at=?, lesson=?, brier_score=? WHERE entry_id=?",
                (status.value, moment.isoformat(), lesson or record.lesson, record.brier_score, entry_id),
            )
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
        return self._entry(row)

    def abandon(self, entry_id: str, *, reason: str, now: datetime | None = None) -> Entry:
        """Stopping is a result too, and an honest one. It is not a silent delete."""
        moment = now or datetime.now(UTC)
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
            if row is None:
                raise KeyError(entry_id)
            if row["status"] != Status.OPEN.value:
                raise PermissionError(f"{entry_id} was already resolved as {row['status']}")
            conn.execute(
                "UPDATE journal_entries SET status=?, resolved_at=?, lesson=? WHERE entry_id=?",
                (Status.ABANDONED.value, moment.isoformat(), reason, entry_id),
            )
            row = conn.execute("SELECT * FROM journal_entries WHERE entry_id=?", (entry_id,)).fetchone()
        return self._entry(row)

    # --- reading -------------------------------------------------------------

    def entries(self, *, status: Status | None = None) -> tuple[Entry, ...]:
        query = "SELECT * FROM journal_entries"
        params: tuple = ()
        if status is not None:
            query += " WHERE status=?"
            params = (status.value,)
        query += " ORDER BY created_at"
        with self._connect() as conn:
            return tuple(self._entry(row) for row in conn.execute(query, params).fetchall())

    def due(self, *, now: datetime | None = None) -> tuple[Entry, ...]:
        """Open decisions whose horizon has passed: the activity/result detector."""
        moment = now or datetime.now(UTC)
        return tuple(e for e in self.entries(status=Status.OPEN)
                     if datetime.fromisoformat(e.due_at) <= moment)

    def _chain(self) -> tuple[Entry, ...]:
        """Entries in the order they were written, which is the order they were chained.

        Not the order they are read in. `entries()` sorts by created_at so the
        journal reads chronologically, but created_at is supplied by the caller:
        recording a decision after the fact -- add(now=yesterday) -- put an entry
        before one it was chained behind, and verify() then called an untouched
        journal rewritten. A hash chain follows insertion, nothing else.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM journal_entries ORDER BY rowid").fetchall()
        return tuple(self._entry(row) for row in rows)

    def verify(self) -> bool:
        """Has any prediction been rewritten since it was made?"""
        previous = ""
        for entry in self._chain():
            payload = {
                "entry_id": entry.entry_id, "title": entry.title, "action": entry.action,
                "predicted": entry.predicted, "probability": entry.probability, "tier": entry.tier.value,
                "cost_hours": entry.cost_hours, "horizon_days": entry.horizon_days,
                "created_at": entry.created_at,
            }
            if entry.previous_fingerprint != previous or _fingerprint(payload, previous) != entry.fingerprint:
                return False
            previous = entry.fingerprint
        return True

    def summary_line(self, *, now: datetime | None = None) -> str:
        """One line, short enough for a shell prompt.

        A journal you have to remember to open is a journal you stop opening.
        This is meant to be printed by your shell profile, so the number of
        decisions you have not faced is in front of you whether you want it or
        not.
        """
        report = self.review(now=now)
        if not report["decisions"]:
            return "SINGULAR · journal vide"
        parts = []
        overdue = report["overdue"]
        parts.append(f"{overdue} à trancher" if overdue else "rien à trancher")
        if report["hours_unresolved"]:
            parts.append(f"{report['hours_unresolved']:g}h sans verdict")
        if report["overconfidence"] is not None and abs(report["overconfidence"]) >= 0.1:
            parts.append(f"calibration {report['overconfidence']:+.0%}")
        return "SINGULAR · " + " · ".join(parts)

    def export_rows(self) -> list[dict]:
        """Every entry, flat, for a spreadsheet or anything else."""
        return [
            {
                "entry_id": e.entry_id,
                "created_at": e.created_at,
                "due_at": e.due_at,
                "tier": e.tier.value,
                "title": e.title,
                "action": e.action,
                "predicted": e.predicted,
                "probability": e.probability,
                "cost_hours": e.cost_hours,
                "status": e.status.value,
                "resolved_at": e.resolved_at or "",
                "brier_score": "" if e.brier_score is None else e.brier_score,
                "lesson": e.lesson or "",
            }
            for e in self.entries()
        ]

    # --- the part that tells you something you did not know ------------------

    def review(self, *, now: datetime | None = None) -> dict:
        """Where your hours went, and where your confidence is wrong."""
        moment = now or datetime.now(UTC)
        all_entries = self.entries()
        resolved = [e for e in all_entries if e.status in (Status.HAPPENED, Status.DID_NOT_HAPPEN)]
        open_entries = [e for e in all_entries if e.is_open]
        abandoned = [e for e in all_entries if e.status is Status.ABANDONED]

        by_tier: dict[str, dict] = {}
        for tier in Tier:
            items = [e for e in all_entries if e.tier is tier]
            if not items:
                continue
            settled = [e for e in items if e.status in (Status.HAPPENED, Status.DID_NOT_HAPPEN)]
            worked = [e for e in settled if e.status is Status.HAPPENED]
            by_tier[tier.value] = {
                "rank": tier.rank,
                "decisions": len(items),
                "hours": round(sum(e.cost_hours for e in items), 1),
                "hours_that_worked": round(sum(e.cost_hours for e in worked), 1),
                "hours_unresolved": round(sum(e.cost_hours for e in items if e.is_open), 1),
                "hit_rate": round(len(worked) / len(settled), 2) if settled else None,
            }

        brier = [e.brier_score for e in resolved if e.brier_score is not None]
        mean_probability = sum(e.probability for e in resolved) / len(resolved) if resolved else None
        hit_rate = sum(1 for e in resolved if e.status is Status.HAPPENED) / len(resolved) if resolved else None

        return {
            "decisions": len(all_entries),
            "open": len(open_entries),
            "overdue": len(self.due(now=moment)),
            "abandoned": len(abandoned),
            "resolved": len(resolved),
            "hours_total": round(sum(e.cost_hours for e in all_entries), 1),
            "hours_unresolved": round(sum(e.cost_hours for e in open_entries), 1),
            "hours_that_worked": round(sum(e.cost_hours for e in resolved if e.status is Status.HAPPENED), 1),
            "mean_brier": round(sum(brier) / len(brier), 4) if brier else None,
            "mean_probability": round(mean_probability, 2) if mean_probability is not None else None,
            "hit_rate": round(hit_rate, 2) if hit_rate is not None else None,
            "overconfidence": round(mean_probability - hit_rate, 2)
            if mean_probability is not None and hit_rate is not None else None,
            "by_tier": by_tier,
            "chain_intact": self.verify(),
        }

    # --- plumbing ------------------------------------------------------------

    @staticmethod
    def _head(conn: sqlite3.Connection) -> str:
        row = conn.execute("SELECT fingerprint FROM journal_entries ORDER BY rowid DESC LIMIT 1").fetchone()
        return "" if row is None else row["fingerprint"]

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(
            row["entry_id"], row["title"], row["action"], row["predicted"], float(row["probability"]),
            Tier(row["tier"]), float(row["cost_hours"]), int(row["horizon_days"]), row["created_at"],
            row["due_at"], Status(row["status"]), row["resolved_at"], row["lesson"],
            None if row["brier_score"] is None else float(row["brier_score"]),
            row["previous_fingerprint"], row["fingerprint"],
        )


__all__ = ["DEFAULT_PATH", "SCHEMA_VERSION", "DecisionJournal", "Entry", "Status", "Tier"]
