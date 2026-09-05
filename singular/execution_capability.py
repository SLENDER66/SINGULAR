"""Capability bindings for executable SINGULAR artifacts.

A textual module/name is descriptive, not an authority, so an executable
validated trajectory binds to an opaque capability token registered against the
exact callable or provider allowed to execute. That token is only half of an
identity: it lives in one process, while the decision that names it and the
attestation that authorizes it are durable.

The gap that opens is a restart. The in-memory table starts empty, so an old
token plus a freshly registered arbitrary object used to become a valid
authorization -- the token said nothing about *which code* it meant. A durable
record of the artifact fingerprint closes it: the token keeps meaning the
artifact it was first bound to, across restarts, and a re-registration under the
same token is only accepted when it presents the same artifact.

What a fingerprint covers and what it does not: it identifies the code object
(module, qualified name, and a hash of its bytecode or its class's), the
interpreter version it was compiled for, and -- for a closure -- the values it
captured, so that two handlers built by the same factory with different
arguments are not mistaken for each other. Captures whose value cannot be
canonicalised deterministically (a live connection, an arbitrary object) are
recorded as opaque and therefore do not distinguish those targets; that is a
stated limit, exercised by a test, rather than a silent one.

Class bytecode says nothing about what an instance holds, so two providers of
the same class pointing at different endpoints were the same artifact by this
measure: after a restart, re-registering the token against a differently
configured instance satisfied both the durable record and the decision that
named it. An artifact can close that for itself by exposing
`artifact_identity()`, whose canonicalised result joins the fingerprint. It
stays opt-in: an object that declares nothing is fingerprinted exactly as
before, and what it holds stays uncovered. The fingerprint answers "is this the
same implementation, configured the way it was authorized", never "will it
behave the same way".
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe
from threading import RLock
from typing import Any

from .sqlite_support import SqliteLocation

SCHEMA_VERSION = 1

#: Interpreter identity, so a capability bound under one runtime is not silently
#: honoured under another whose bytecode means something different.
RUNTIME_VERSION = f"cpython-{sys.version_info.major}.{sys.version_info.minor}"


#: Types whose value can be canonicalised into a fingerprint deterministically.
#: Anything else is recorded as opaque -- see _closure_identity.
_CANONICAL_TYPES = (str, int, float, bool, bytes, type(None))


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int, float)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (tuple, list, frozenset, set)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=repr) if isinstance(value, (frozenset, set)) else items
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    return {"__opaque__": type(value).__qualname__}


def _closure_identity(func: Any) -> list[Any]:
    """What a closure captured, when that can be stated deterministically.

    Bytecode alone does not distinguish two closures produced by the same
    factory: make(1) and make(2) share a module, a qualified name and every
    instruction, yet do different things. Capturing the values closes that,
    for captures whose value can be canonicalised. Captures that cannot -- a
    live connection, an arbitrary object -- are recorded as opaque, which is a
    stated limit rather than a silent one.
    """
    code = getattr(func, "__code__", None)
    cells = getattr(func, "__closure__", None)
    if code is None or not cells:
        return []
    captured: list[Any] = []
    for name, cell in zip(getattr(code, "co_freevars", ()), cells, strict=False):
        try:
            captured.append([name, _canonical_value(cell.cell_contents)])
        except ValueError:
            captured.append([name, {"__empty_cell__": True}])
    return captured


def _code_identity(target: Any) -> tuple[str, str, str, bytes, list[Any]]:
    """(kind, module, qualname, code bytes, captured state) for a target."""
    code = getattr(target, "__code__", None)
    if code is not None:
        return ("callable", getattr(target, "__module__", "") or "", getattr(target, "__qualname__", "") or "",
                bytes(code.co_code), _closure_identity(target))
    func = getattr(target, "__func__", None)
    if func is not None and getattr(func, "__code__", None) is not None:
        return ("method", getattr(func, "__module__", "") or "", getattr(func, "__qualname__", "") or "",
                bytes(func.__code__.co_code), _closure_identity(func))
    kind = type(target)
    parts: list[bytes] = []
    for name in sorted(dir(kind)):
        if name.startswith("__"):
            continue
        member = getattr(kind, name, None)
        member_code = getattr(member, "__code__", None)
        if member_code is not None:
            parts.append(name.encode("utf-8") + b"\x1f" + bytes(member_code.co_code))
    return ("object", kind.__module__, kind.__qualname__, b"\x1e".join(parts), [])


def _declared_identity(target: Any) -> Any:
    """What an artifact says its configuration is, when it offers to say it.

    Opt-in on purpose. Reading an instance's attributes wholesale would fold
    mutable working state into the identity, so a counter ticking during a run
    would revoke the artifact mid-execution; an artifact that declares its own
    configuration states what is meant to be stable about it. A declaration that
    cannot be produced is refused rather than skipped: an object that started to
    answer the question and failed is not the same as one that never claimed to.
    """
    declare = getattr(target, "artifact_identity", None)
    if not callable(declare):
        return None
    try:
        declared = declare()
    except Exception as exc:
        raise ValueError(f"artifact identity could not be established: {exc}") from exc
    if declared is None:
        raise ValueError("artifact identity declared nothing")
    return _canonical_value(declared)


def artifact_fingerprint(target: Any) -> str:
    """A stable identity for the code a capability token stands for."""
    if target is None:
        raise ValueError("an execution target is required")
    kind, module, qualname, code, captured = _code_identity(target)
    payload = {
        "kind": kind,
        "module": module,
        "qualname": qualname,
        "runtime": RUNTIME_VERSION,
        "code": hashlib.sha256(code).hexdigest(),
        "captured": captured,
    }
    declared = _declared_identity(target)
    if declared is not None:
        # Absent when nothing is declared, so every artifact that predates this
        # keeps the fingerprint it already had: no durable record is invalidated.
        payload["declared"] = declared
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    artifact_fingerprint: str
    artifact_kind: str
    module: str
    qualname: str
    runtime_version: str
    epoch: int
    status: str
    created_at: str
    revoked_at: str | None = None

    @property
    def active(self) -> bool:
        return self.status == "ACTIVE"


class DurableCapabilityStore:
    """What a capability token means, across restarts."""

    def __init__(self, path: str | Path = "data/singular.db") -> None:
        self._location = SqliteLocation(path)
        self.path = self._location.reference
        self._init_schema()

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        return self._location.session()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS execution_capability_schema (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM execution_capability_schema").fetchone()
            if row is None:
                conn.execute("INSERT INTO execution_capability_schema(version) VALUES(?)", (SCHEMA_VERSION,))
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"execution capability schema v{int(row['version'])} does not match v{SCHEMA_VERSION}; refusing to read it"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_capabilities (
                    capability_id TEXT PRIMARY KEY,
                    artifact_fingerprint TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    module TEXT NOT NULL,
                    qualname TEXT NOT NULL,
                    runtime_version TEXT NOT NULL,
                    epoch INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )

    def get(self, capability_id: str) -> CapabilityRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_capabilities WHERE capability_id=?", (capability_id,)).fetchone()
        return None if row is None else self._record(row)

    def bind(self, capability_id: str, target: Any) -> CapabilityRecord:
        """Bind a token to an artifact, or confirm it already means that artifact.

        A token that already stands for one artifact can never be pointed at
        another: that is the restart bypass. A revoked token is never re-bound --
        rotation issues a new token rather than reviving a retired one.
        """
        fingerprint = artifact_fingerprint(target)
        kind, module, qualname, _, _ = _code_identity(target)
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_capabilities WHERE capability_id=?", (capability_id,)).fetchone()
            if row is not None:
                record = self._record(row)
                if record.status == "REVOKED":
                    raise PermissionError("a revoked capability id cannot be re-registered")
                if record.artifact_fingerprint != fingerprint:
                    raise PermissionError("capability id is already bound to a different executable artifact")
                if record.runtime_version != RUNTIME_VERSION:
                    raise PermissionError("capability was registered under a different runtime version")
                return record
            conn.execute(
                "INSERT INTO execution_capabilities(capability_id,artifact_fingerprint,artifact_kind,module,qualname,runtime_version,epoch,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (capability_id, fingerprint, kind, module, qualname, RUNTIME_VERSION, 1, "ACTIVE", now),
            )
        return CapabilityRecord(capability_id, fingerprint, kind, module, qualname, RUNTIME_VERSION, 1, "ACTIVE", now)

    def revoke(self, capability_id: str) -> CapabilityRecord:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE execution_capabilities SET status='REVOKED', revoked_at=? WHERE capability_id=? AND status='ACTIVE'",
                (now, capability_id),
            )
            if cur.rowcount != 1:
                raise KeyError(capability_id)
            row = conn.execute("SELECT * FROM execution_capabilities WHERE capability_id=?", (capability_id,)).fetchone()
        return self._record(row)

    def verify(self, capability_id: str, target: Any) -> bool:
        """Is this token still active and still meaning this artifact?"""
        record = self.get(capability_id)
        if record is None or not record.active:
            return False
        if record.runtime_version != RUNTIME_VERSION:
            return False
        try:
            return record.artifact_fingerprint == artifact_fingerprint(target)
        except ValueError:
            return False

    @staticmethod
    def _record(row: sqlite3.Row) -> CapabilityRecord:
        return CapabilityRecord(
            row["capability_id"], row["artifact_fingerprint"], row["artifact_kind"], row["module"], row["qualname"],
            row["runtime_version"], int(row["epoch"]), row["status"], row["created_at"], row["revoked_at"],
        )


class ExecutionCapabilityRegistry:
    """Bind opaque capability ids to exact in-process execution objects.

    The in-memory table answers "is this the very object that was registered".
    A durable store, when one is attached, answers the question that survives a
    restart: "is this the artifact the token has always meant".
    """

    def __init__(self, durable: DurableCapabilityStore | None = None) -> None:
        self._lock = RLock()
        self._targets: dict[str, Any] = {}
        self._by_object: dict[int, str] = {}
        self._fingerprints: dict[str, str] = {}
        self.durable = durable

    def attach(self, durable: DurableCapabilityStore) -> None:
        """Give an existing registry a durable meaning for the tokens it holds."""
        with self._lock:
            for capability_id, target in self._targets.items():
                durable.bind(capability_id, target)
            self.durable = durable

    def register(self, target: Any, capability_id: str | None = None) -> str:
        if target is None:
            raise ValueError("an execution target is required")
        with self._lock:
            existing = self._by_object.get(id(target))
            if existing is not None and self._targets.get(existing) is target:
                if capability_id is not None and capability_id != existing:
                    raise ValueError("target is already bound to a different capability")
                return existing
            token = capability_id or f"cap_{token_urlsafe(24)}"
            if not token.strip():
                raise ValueError("capability id cannot be empty")
            bound = self._targets.get(token)
            if bound is not None and bound is not target:
                raise ValueError("capability id is already bound to another target")
            fingerprint = artifact_fingerprint(target)
            if self.durable is not None:
                self.durable.bind(token, target)
            self._targets[token] = target
            self._by_object[id(target)] = token
            self._fingerprints[token] = fingerprint
            return token

    def matches(self, capability_id: str, target: Any) -> bool:
        if not capability_id or target is None:
            return False
        with self._lock:
            if self._targets.get(capability_id) is not target:
                return False
            if self._fingerprints.get(capability_id) != artifact_fingerprint(target):
                return False
            durable = self.durable
        # Read the durable record outside the lock: it is the authority on
        # revocation, and it is re-read on every check so a token revoked between
        # validation and execution stops matching immediately.
        return True if durable is None else durable.verify(capability_id, target)

    def fingerprint_of(self, capability_id: str) -> str | None:
        with self._lock:
            return self._fingerprints.get(capability_id)

    def revoke(self, capability_id: str) -> None:
        with self._lock:
            target = self._targets.pop(capability_id, None)
            self._fingerprints.pop(capability_id, None)
            if target is not None:
                self._by_object.pop(id(target), None)
            durable = self.durable
        if durable is not None:
            try:
                durable.revoke(capability_id)
            except KeyError:
                pass


GLOBAL_EXECUTION_CAPABILITIES = ExecutionCapabilityRegistry()


def register_execution_capability(target: Any, capability_id: str | None = None) -> str:
    return GLOBAL_EXECUTION_CAPABILITIES.register(target, capability_id)


def execution_capability_matches(capability_id: str, target: Any) -> bool:
    return GLOBAL_EXECUTION_CAPABILITIES.matches(capability_id, target)


__all__ = [
    "GLOBAL_EXECUTION_CAPABILITIES",
    "RUNTIME_VERSION",
    "SCHEMA_VERSION",
    "CapabilityRecord",
    "DurableCapabilityStore",
    "ExecutionCapabilityRegistry",
    "artifact_fingerprint",
    "execution_capability_matches",
    "register_execution_capability",
]
