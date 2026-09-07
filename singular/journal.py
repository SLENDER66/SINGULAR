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
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from math import isfinite
from pathlib import Path

from .learning import Forecast, ForecastKind, LearningEngine
from .sqlite_support import SqliteLocation

SCHEMA_VERSION = 2
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

    @property
    def label(self) -> str:
        """Le nom du rang tel qu'il est écrit dans la constitution.

        Les valeurs stockées sont sans accent, pour qu'une base écrite hier
        reste lisible demain quel que soit l'encodage. Ce qu'on montre à
        l'écran, lui, doit être le mot juste.
        """
        return {
            Tier.STABILITE: "Stabilité",
            Tier.REVENUS: "Revenus",
            Tier.CAPACITES: "Capacités",
            Tier.OPPORTUNITES: "Opportunités",
            Tier.PATRIMOINE: "Patrimoine",
            Tier.LIBERTE: "Liberté",
        }[self]


class Status(str, Enum):
    OPEN = "OPEN"
    HAPPENED = "HAPPENED"
    DID_NOT_HAPPEN = "DID_NOT_HAPPEN"
    ABANDONED = "ABANDONED"


class Reversibility(str, Enum):
    """Peut-on revenir en arrière, et à quel prix ?

    La constitution dit : « En cas d'incertitude critique et de conséquence
    élevée : HALT. » Rien dans une décision ne permettait de l'appliquer. Le
    journal savait ce qu'une décision coûte en heures ; jamais ce que coûte de
    s'être trompé. Une dette est l'exemple le plus net : deux décisions à
    5 000 euros et 20 heures ne sont pas la même décision selon qu'on peut
    l'annuler la semaine suivante ou qu'on la rembourse pendant trois ans.

    Les valeurs stockées sont sans accent, comme celles de `Tier` : une base
    écrite aujourd'hui doit rester lisible quel que soit l'encodage.
    """

    REVERSIBLE = "REVERSIBLE"
    COUTEUSE = "COUTEUSE"
    IRREVERSIBLE = "IRREVERSIBLE"

    @property
    def label(self) -> str:
        return {
            Reversibility.REVERSIBLE: "réversible",
            Reversibility.COUTEUSE: "coûteuse à défaire",
            Reversibility.IRREVERSIBLE: "irréversible",
        }[self]


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
    #: En euros. `None` veut dire « pas chiffré », pas « zéro » : une décision
    #: dont on n'a pas estimé le gain n'est pas une décision sans gain, et les
    #: confondre effacerait justement ce que la Notice doit reprocher.
    expected_gain_eur: float | None = None
    reversibility: Reversibility | None = None

    @property
    def is_open(self) -> bool:
        return self.status is Status.OPEN

    def overdue_days(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        return max(0, (moment - datetime.fromisoformat(self.due_at)).days)


def _fingerprint(payload: dict, previous: str) -> str:
    material = json.dumps({"previous": previous, **payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _payload(
    *,
    entry_id: str, title: str, action: str, predicted: str, probability: float,
    tier: str, cost_hours: float, horizon_days: int, created_at: str,
    expected_gain_eur: float | None, reversibility: str | None,
) -> dict:
    """La matière que l'empreinte signe. Écrite une fois, lue par les deux côtés.

    Elle l'était deux fois -- dans `add()` et dans `verify()` -- et deux copies
    d'une même vérité finissent par diverger. Ajouter un champ à l'une aurait
    déclaré réécrit un journal auquel personne n'a touché, définitivement,
    puisque les entrées ne sont jamais réécrites.

    Les deux champs d'affaires n'entrent dans la charge que lorsqu'ils sont
    renseignés. C'est ce qui permet à une entrée écrite avant qu'ils existent
    de rester vérifiable : sa charge est exactement celle d'hier, à l'octet
    près. Et c'est aussi ce qui fait qu'une valeur glissée après coup dans la
    base change la charge, donc l'empreinte : `verify()` la voit. Un gain
    attendu qu'on pourrait réviser une fois le résultat connu n'apprendrait
    rien -- c'est la raison d'être de la chaîne.
    """
    payload = {
        "entry_id": entry_id, "title": title, "action": action, "predicted": predicted,
        "probability": probability, "tier": tier, "cost_hours": cost_hours,
        "horizon_days": horizon_days, "created_at": created_at,
    }
    if expected_gain_eur is not None:
        payload["expected_gain_eur"] = expected_gain_eur
    if reversibility is not None:
        payload["reversibility"] = reversibility
    return payload


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
            # Le verrou d'ecriture d'abord, et explicitement. Sans lui, le
            # controle et l'action de la migration ne sont pas dans la meme
            # section critique : `PRAGMA table_info` dit « colonne absente » a
            # deux processus a la fois, et le second `ALTER TABLE` echoue en
            # « duplicate column name ».
            #
            # Ce n'est pas theorique : le Sage tourne pendant qu'on tape `add`
            # dans une autre fenetre, et les deux migrent au premier lancement
            # apres une mise a jour. On avait cru la sequence protegee par le
            # `CREATE TABLE IF NOT EXISTS` ci-dessous -- SQLite l'optimise en
            # rien du tout quand la table existe, et ne prend alors aucun
            # verrou. C'est le test de concurrence qui l'a montre, apres avoir
            # ete pris pour instable.
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS journal_schema (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM journal_schema").fetchone()
            if row is None:
                conn.execute("INSERT INTO journal_schema(version) VALUES(?)", (SCHEMA_VERSION,))
            else:
                self._migrate(conn, int(row["version"]))
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
                    fingerprint TEXT NOT NULL,
                    expected_gain_eur REAL,
                    reversibility TEXT
                )
                """
            )

    @staticmethod
    def _migrate(conn: sqlite3.Connection, version: int) -> None:
        """Fait passer une base existante à la version courante, ou refuse.

        `CREATE TABLE IF NOT EXISTS` ne migre rien : il ne s'exécute pas quand
        la table est là, et une base d'hier serait restée sans les colonnes
        neuves pendant que le code les lit. `CLAUDE.md` §13 l'interdit
        explicitement.

        Ce qui est ajouté ici est ajouté en NULL. C'est voulu : une décision
        prise avant que le gain attendu existe n'a pas de gain attendu, et lui
        en inventer un -- zéro compris -- réécrirait l'histoire. Sa charge
        d'empreinte reste donc celle de la v1, et la chaîne tient.
        """
        if version == SCHEMA_VERSION:
            return
        if version > SCHEMA_VERSION or version < 1:
            raise RuntimeError(f"journal schema v{version} does not match v{SCHEMA_VERSION}")

        if version == 1:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "journal_entries" in tables:
                colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(journal_entries)")}
                if "expected_gain_eur" not in colonnes:
                    conn.execute("ALTER TABLE journal_entries ADD COLUMN expected_gain_eur REAL")
                if "reversibility" not in colonnes:
                    conn.execute("ALTER TABLE journal_entries ADD COLUMN reversibility TEXT")
            version = 2

        conn.execute("UPDATE journal_schema SET version=?", (version,))

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
        expected_gain_eur: float | None = None,
        reversibility: Reversibility | None = None,
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
        # Le gain reste facultatif -- l'exiger ferait enregistrer moins de
        # décisions, et une décision non écrite est pire qu'une décision sans
        # chiffre. Mais un chiffre donné doit être un nombre : NaN se propage
        # sans lever, et un total de gains contaminé par un NaN reste NaN sans
        # que rien ne le signale.
        if expected_gain_eur is not None:
            if not isfinite(expected_gain_eur):
                raise ValueError("expected_gain_eur must be finite")
            if expected_gain_eur < 0:
                raise ValueError("expected_gain_eur cannot be negative: a cost is not a gain")
        if reversibility is not None and not isinstance(reversibility, Reversibility):
            raise TypeError("reversibility must be a Reversibility, not a bare string")

        # Canonicalise before fingerprinting, because the row is read back
        # canonicalised. `add(cost_hours=60)` fingerprinted the integer 60 and
        # `_entry` returned 60.0, which json renders differently, so verify()
        # declared an untouched journal rewritten -- from its very first entry,
        # for ever, since entries are never rewritten. The CLI passes floats and
        # never saw it; any other caller broke the chain by writing to it.
        # Validation runs first, so a string still raises rather than being
        # quietly converted into a number.
        probability = float(probability)
        cost_hours = float(cost_hours)
        horizon_days = int(horizon_days)
        # Même raison que ci-dessus : add(expected_gain_eur=5000) signerait
        # l'entier 5000 quand la ligne relue rend 5000.0.
        if expected_gain_eur is not None:
            expected_gain_eur = float(expected_gain_eur)

        moment = now or datetime.now(UTC)
        entry_id = "DEC-" + uuid.uuid4().hex[:8]
        payload = _payload(
            entry_id=entry_id, title=title, action=action, predicted=predicted,
            probability=probability, tier=tier.value, cost_hours=cost_hours,
            horizon_days=horizon_days, created_at=moment.isoformat(),
            expected_gain_eur=expected_gain_eur,
            reversibility=None if reversibility is None else reversibility.value,
        )
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
                "created_at,due_at,status,resolved_at,lesson,brier_score,previous_fingerprint,fingerprint,"
                "expected_gain_eur,reversibility)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry_id, title, action, predicted, probability, tier.value, cost_hours, horizon_days,
                 moment.isoformat(), due, Status.OPEN.value, None, None, None, previous, fingerprint,
                 expected_gain_eur, None if reversibility is None else reversibility.value),
            )
        return Entry(entry_id, title, action, predicted, probability, tier, cost_hours, horizon_days,
                     moment.isoformat(), due, Status.OPEN, None, None, None, previous, fingerprint,
                     expected_gain_eur, reversibility)

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
            payload = _payload(
                entry_id=entry.entry_id, title=entry.title, action=entry.action,
                predicted=entry.predicted, probability=entry.probability, tier=entry.tier.value,
                cost_hours=entry.cost_hours, horizon_days=entry.horizon_days,
                created_at=entry.created_at, expected_gain_eur=entry.expected_gain_eur,
                reversibility=None if entry.reversibility is None else entry.reversibility.value,
            )
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
                "expected_gain_eur": "" if e.expected_gain_eur is None else e.expected_gain_eur,
                "reversibility": "" if e.reversibility is None else e.reversibility.value,
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
            # Le raisonnement d'affaires, tel que la constitution le demande :
            # « Optimisation : options, levier, coût, vitesse, réversibilité. »
            # Le coût et la vitesse étaient là depuis le début ; ce qui suit
            # est ce qui manquait pour qu'une décision puisse être jugée sur
            # autre chose que le temps qu'elle prend.
            "gain_expected_total": round(
                sum(e.expected_gain_eur for e in all_entries if e.expected_gain_eur is not None), 2),
            "gain_expected_open": round(
                sum(e.expected_gain_eur for e in open_entries if e.expected_gain_eur is not None), 2),
            "hours_without_gain": round(
                sum(e.cost_hours for e in all_entries if e.expected_gain_eur is None), 1),
            "irreversible_open": sum(
                1 for e in open_entries if e.reversibility is Reversibility.IRREVERSIBLE),
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
            None if row["expected_gain_eur"] is None else float(row["expected_gain_eur"]),
            None if row["reversibility"] is None else Reversibility(row["reversibility"]),
        )


__all__ = ["DEFAULT_PATH", "SCHEMA_VERSION", "DecisionJournal", "Entry", "Reversibility", "Status", "Tier"]
