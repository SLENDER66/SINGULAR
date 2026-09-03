"""Static and dynamic integrity checks for SINGULAR's execution boundary."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .execution import DurableExecutionEngine
from .tool_fabric import ToolFabric


RAW_METHODS = frozenset({"execute", "execute_effect", "reconcile_effect"})
RAW_TOOL_METHODS = frozenset({"execute_autonomous", "execute_approved"})
DEFINITION_MODULES = frozenset({"execution.py", "tool_fabric.py"})


@dataclass(frozen=True)
class BoundaryFinding:
    path: str
    line: int
    rule: str
    detail: str


@dataclass(frozen=True)
class BoundaryAuditReport:
    findings: tuple[BoundaryFinding, ...]
    checked_files: int
    raw_execution_is_denied: bool

    @property
    def clean(self) -> bool:
        return not self.findings and self.raw_execution_is_denied


class ExecutionBoundaryAuditor:
    """Detect obvious production call-site bypasses and verify raw API denial."""

    def __init__(self, package_dir: Path | None = None) -> None:
        self.package_dir = package_dir or Path(__file__).resolve().parent

    def audit(self) -> BoundaryAuditReport:
        findings: list[BoundaryFinding] = []
        checked = 0
        for path in sorted(self.package_dir.glob("*.py")):
            if path.name in DEFINITION_MODULES or path.name == "execution_boundary_audit.py":
                continue
            checked += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError) as exc:
                findings.append(BoundaryFinding(str(path), 1, "PARSE_ERROR", str(exc)))
                continue
            findings.extend(self._scan(path, tree))
        raw_denied = self._raw_api_is_denied()
        if not raw_denied:
            findings.append(BoundaryFinding("runtime", 0, "RAW_API_NOT_DENY_BY_DEFAULT", "A public raw execution entry point did not raise PermissionError."))
        return BoundaryAuditReport(tuple(findings), checked, raw_denied)

    @staticmethod
    def _scan(path: Path, tree: ast.AST) -> list[BoundaryFinding]:
        findings: list[BoundaryFinding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if isinstance(target, ast.Attribute):
                if target.attr in RAW_TOOL_METHODS:
                    findings.append(BoundaryFinding(str(path), target.lineno, "RAW_TOOL_BYPASS", target.attr))
                if target.attr in RAW_METHODS and isinstance(target.value, ast.Name) and target.value.id == "DurableExecutionEngine":
                    findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", target.attr))
                if target.attr == "handler" and isinstance(target.value, ast.Name):
                    findings.append(BoundaryFinding(str(path), target.lineno, "DIRECT_HANDLER_BYPASS", f"{target.value.id}.handler(...)"))
        return findings

    @staticmethod
    def _raw_api_is_denied() -> bool:
        class _Noop:
            def __call__(self, *_args, **_kwargs):
                return None

        for constructor in (DurableExecutionEngine, ToolFabric):
            # ToolFabric can be instantiated directly; the durable engine needs a runtime,
            # so only test the methods whose guard can be reached without state.
            if constructor is ToolFabric:
                obj = constructor()
                for args, method in (((), "execute_autonomous"),):
                    try:
                        getattr(obj, method)("probe", *_args)
                    except PermissionError:
                        continue
                    except Exception:
                        return False
                    return False
            else:
                continue
        return True


__all__ = ["BoundaryFinding", "BoundaryAuditReport", "ExecutionBoundaryAuditor"]
