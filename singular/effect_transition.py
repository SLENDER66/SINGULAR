from __future__ import annotations

import json
import sqlite3
from typing import Any

from .effects import EffectStatus, ExternalEffectCoordinator
from .sqlite_support import SqliteLocation


def transition(self: ExternalEffectCoordinator, key: str, status: str, *, result: Any = None, error: str | None = None) -> None:
    """Apply a state transition atomically; repeating the same state preserves evidence."""
    with SqliteLocation(self.store.path).connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM external_effects WHERE provider_idempotency_key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        current = row["status"]
        if status == current:
            return
        if status not in self._TRANSITIONS.get(current, frozenset()):
            if current in {EffectStatus.COMPLETED.value, EffectStatus.FAILED.value}:
                raise RuntimeError(f"Transition d'effet perdue : état terminal déjà atteint ({current} -> {status}).")
            raise ValueError(f"Transition d'effet interdite : {current} -> {status}")
        encoded = None if result is None else json.dumps(result, sort_keys=True, default=str)
        cur = conn.execute(
            "UPDATE external_effects SET status=?,result=?,error=?,updated_at=? WHERE provider_idempotency_key=? AND status=?",
            (status, encoded, error, self._now(), key, current),
        )
        if cur.rowcount != 1:
            raise RuntimeError("La transition d'effet a échoué à cause d'une concurrence d'état.")


ExternalEffectCoordinator._transition = transition
