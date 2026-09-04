"""Where a SQLite-backed store actually keeps its database.

SQLite's ``":memory:"`` is scoped to a single *connection*. Every store in this
package opens a fresh connection per operation, so a store constructed with
``":memory:"`` wrote its schema into a connection it immediately dropped and
answered every later query from a brand new, empty database.

That failure is silent and points the wrong way. An idempotency lookup, an
execution record or an approval binding coming back empty does not read as
"broken store", it reads as "never seen before" -- which is exactly the
condition under which the durable boundary is willing to execute. A store whose
reads always return nothing is a fail-open persistence mode, not merely a
non-functional one.

Resolve ``":memory:"`` once into a named shared-cache URI kept alive by an
anchor connection, and hand that URI on to derived stores through their ``path``
so they join the same database instead of each minting their own. Anchors live
for the lifetime of the process: an in-memory database that vanished while a
store still referenced it would reintroduce the same empty-read behaviour.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

MEMORY_PATH = ":memory:"
_MEMORY_URI_PREFIX = "file:singular_memory_"
_MEMORY_URI_SUFFIX = "?mode=memory&cache=shared"

#: Keeps every shared in-memory database alive for the process lifetime.
_ANCHORS: dict[str, sqlite3.Connection] = {}


def is_shared_memory_target(raw: str) -> bool:
    """True for any shared in-memory URI, not only the ones minted here.

    A `mode=memory` URI that fell through to the file branch would be created on
    disk under that literal name, which is both surprising and a way to smuggle
    an unanchored database past this module.
    """
    return raw.startswith("file:") and "mode=memory" in raw


class SqliteLocation:
    """The resolved location of one store's database, safe to share."""

    __slots__ = ("target", "uri", "reference")

    def __init__(self, path: str | Path) -> None:
        raw = str(path)
        if raw == MEMORY_PATH:
            self.target = f"{_MEMORY_URI_PREFIX}{uuid4().hex}{_MEMORY_URI_SUFFIX}"
            self.uri = True
            self.reference: str | Path = self.target
            self._anchor()
        elif is_shared_memory_target(raw):
            self.target = raw
            self.uri = True
            self.reference = raw
            self._anchor()
        else:
            resolved = Path(path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self.target = str(resolved)
            self.uri = False
            self.reference = resolved

    def _anchor(self) -> None:
        if self.target not in _ANCHORS:
            anchor = sqlite3.connect(self.target, uri=True, timeout=10.0)
            anchor.row_factory = sqlite3.Row
            _ANCHORS[self.target] = anchor

    def connect(self, *, foreign_keys: bool = False, busy_timeout: bool = False) -> sqlite3.Connection:
        conn = sqlite3.connect(self.target, uri=self.uri, timeout=10.0)
        conn.row_factory = sqlite3.Row
        if busy_timeout:
            conn.execute("PRAGMA busy_timeout=10000")
        if foreign_keys:
            conn.execute("PRAGMA foreign_keys=ON")
        return conn


__all__ = ["MEMORY_PATH", "SqliteLocation", "is_shared_memory_target"]
