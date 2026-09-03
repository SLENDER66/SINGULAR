"""Process-local capability bindings for executable SINGULAR artifacts.

A textual module/name is descriptive, not an authority. Executable validated
trajectories therefore bind to an opaque capability token registered against
the exact callable/provider object that is allowed to execute.
"""
from __future__ import annotations

from secrets import token_urlsafe
from threading import RLock
from typing import Any


class ExecutionCapabilityRegistry:
    """Bind opaque capability ids to exact in-process execution objects."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._targets: dict[str, Any] = {}
        self._by_object: dict[int, str] = {}

    def register(self, target: Any, capability_id: str | None = None) -> str:
        if target is None:
            raise ValueError("an execution target is required")
        with self._lock:
            existing = self._by_object.get(id(target))
            if existing is not None:
                if capability_id is not None and capability_id != existing:
                    raise ValueError("target is already bound to a different capability")
                return existing
            token = capability_id or f"cap_{token_urlsafe(24)}"
            if not token.strip():
                raise ValueError("capability id cannot be empty")
            bound = self._targets.get(token)
            if bound is not None and bound is not target:
                raise ValueError("capability id is already bound to another target")
            self._targets[token] = target
            self._by_object[id(target)] = token
            return token

    def matches(self, capability_id: str, target: Any) -> bool:
        if not capability_id or target is None:
            return False
        with self._lock:
            return self._targets.get(capability_id) is target

    def revoke(self, capability_id: str) -> None:
        with self._lock:
            target = self._targets.pop(capability_id, None)
            if target is not None:
                self._by_object.pop(id(target), None)


GLOBAL_EXECUTION_CAPABILITIES = ExecutionCapabilityRegistry()


def register_execution_capability(target: Any, capability_id: str | None = None) -> str:
    return GLOBAL_EXECUTION_CAPABILITIES.register(target, capability_id)


def execution_capability_matches(capability_id: str, target: Any) -> bool:
    return GLOBAL_EXECUTION_CAPABILITIES.matches(capability_id, target)


__all__ = [
    "ExecutionCapabilityRegistry",
    "GLOBAL_EXECUTION_CAPABILITIES",
    "register_execution_capability",
    "execution_capability_matches",
]
