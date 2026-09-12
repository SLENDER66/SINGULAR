"""Bounded, read-only tools that JARVIS may request through SINGULAR.

The tool in this module has no external effect. Its capability is registered by
trusted composition, never selected by model output. The execution handler
accepts only an already-validated ``ActionRequest``; the requested path is part
of that action and is therefore bound into the validated decision fingerprint.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..autopilot import ActionRequest
from ..execution_capability import register_execution_capability

DEFAULT_MAX_BYTES = 256 * 1024


def _relative_path(action: ActionRequest) -> Path:
    """Extract and validate ``read:<relative-path>`` from a bound action name."""
    prefix = "read:"
    if not action.name.startswith(prefix):
        raise ValueError("read-only tool action must use the read:<relative-path> form")
    raw = action.name[len(prefix):].strip()
    if not raw:
        raise ValueError("a relative path is required")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise PermissionError("path must stay inside the configured repository")
    return path


def make_read_only_repository_tool(
    root: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    capability_id: str | None = None,
) -> tuple[str, Any]:
    """Create a bounded repository reader and register its execution capability.

    ``root`` and ``max_bytes`` are captured by the handler, so the execution
    capability is tied to this exact configuration. The returned capability id
    is opaque and must be supplied by trusted SINGULAR composition to a
    validated decision; JARVIS/Claude must never invent or choose it.
    """
    repository = Path(root).resolve()
    if not repository.is_dir():
        raise ValueError("repository root must be an existing directory")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    def read_repository_file(action: ActionRequest) -> dict[str, Any]:
        relative = _relative_path(action)
        candidate = (repository / relative).resolve()
        try:
            candidate.relative_to(repository)
        except ValueError:
            raise PermissionError("path escapes the configured repository") from None
        if not candidate.is_file():
            raise FileNotFoundError(str(relative))
        size = candidate.stat().st_size
        if size > max_bytes:
            raise ValueError("file exceeds configured read limit")
        data = candidate.read_text(encoding="utf-8")
        return {
            "path": relative.as_posix(),
            "bytes": len(data.encode("utf-8")),
            "text": data,
        }

    capability = register_execution_capability(
        read_repository_file,
        capability_id,
    )
    return capability, read_repository_file


__all__ = ["DEFAULT_MAX_BYTES", "make_read_only_repository_tool"]
