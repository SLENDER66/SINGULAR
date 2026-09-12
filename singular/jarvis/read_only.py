"""Bounded, read-only tools that JARVIS may request through SINGULAR.

The tool in this module has no external effect. Its capability is registered by
trusted composition, never selected by model output. The execution handler
accepts only an already-validated ``ActionRequest``; the requested path is part
of that action and is therefore bound into the validated decision fingerprint.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

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


def _resolve_inside(repository: Path, relative: Path) -> Path:
    candidate = (repository / relative).resolve()
    try:
        candidate.relative_to(repository)
    except ValueError:
        raise PermissionError("path escapes the configured repository") from None
    return candidate


def _read_bounded_text(candidate: Path, max_bytes: int) -> str:
    """Read a bounded UTF-8 file while refusing a final symlink.

    Resolution and opening are separate filesystem operations. Where the
    platform exposes ``O_NOFOLLOW``, the final path component cannot be swapped
    to a symlink between those operations. Reading through the opened descriptor
    also pins the file object against later pathname replacement.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(candidate, flags)
    try:
        with os.fdopen(fd, "rb") as stream:
            data = stream.read(max_bytes + 1)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    if len(data) > max_bytes:
        raise ValueError("file exceeds configured read limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("read-only repository tool accepts UTF-8 text files only") from exc


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
        candidate = _resolve_inside(repository, relative)
        if not candidate.is_file():
            raise FileNotFoundError(str(relative))
        data = _read_bounded_text(candidate, max_bytes).encode("utf-8")
        text = data.decode("utf-8")
        return {
            "path": relative.as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "text": text,
        }

    capability = register_execution_capability(read_repository_file, capability_id)
    return capability, read_repository_file


def verify_read_only_result(
    root: str | Path,
    action: ActionRequest,
    result: Mapping[str, Any],
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> bool:
    """Independently verify a read result by reopening the requested file.

    This verifier does not trust the handler's success flag or returned text.
    It independently resolves the bound action path, reads the file, recomputes
    size, SHA-256 and decoded text, and compares those facts with the result.
    """
    repository = Path(root).resolve()
    if not repository.is_dir() or max_bytes < 1:
        return False
    try:
        relative = _relative_path(action)
        candidate = _resolve_inside(repository, relative)
        if not candidate.is_file():
            return False
        data = _read_bounded_text(candidate, max_bytes).encode("utf-8")
        text = data.decode("utf-8")
        expected = {
            "path": relative.as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "text": text,
        }
        return all(result.get(key) == value for key, value in expected.items())
    except (OSError, PermissionError, UnicodeDecodeError, ValueError):
        return False


__all__ = ["DEFAULT_MAX_BYTES", "make_read_only_repository_tool", "verify_read_only_result"]
