"""AZAZEL command-line front door.

The implementation is delegated to the governed compatibility runtime. This
keeps one execution/governance path while making AZAZEL the public identity.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..jarvis.cli import main as _legacy_main


def main(argv: Sequence[str] | None = None) -> int:
    """Run AZAZEL through the single existing governed CLI path."""
    return _legacy_main(argv)


__all__ = ["main"]
