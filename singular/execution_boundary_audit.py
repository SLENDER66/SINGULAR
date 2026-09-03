"""Static and dynamic integrity checks for SINGULAR's execution boundary."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .execution import DurableExecutionEngine
from .tool_fabric import ToolFabric


RAW_METHODS = frozenset({"execute", "execute_effect", "reconcile_effect"})
RAW_TOOL_METHODS = frozenset({"execute_autonomous", "execute_approved"})
INNER_VALIDATED_METHODS = frozenset({"execute_validated", "execute_effect_validated", "reconcile_effect_validated"})
DEFINITION_MODULES = frozenset({"execution.py", "tool_fabric.py"})
INNER_ALLOWED_MODULES = frozenset({"validated_execution.py", "validated_decision_service.py"})


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
    """Detect production execution bypasses and verify raw API denial."""

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
        durable_engine_receivers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                constructor = node.value.func
                if isinstance(constructor, ast.Name) and constructor.id == "DurableExecutionEngine":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            durable_engine_receivers.add(target.id)

        inner_allowed = path.name in INNER_ALLOWED_MODULES
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            target = node.func
            receiver = target.value
            if target.attr in RAW_TOOL_METHODS:
                findings.append(BoundaryFinding(str(path), target.lineno, "RAW_TOOL_BYPASS", target.attr))
            if target.attr in {"execute_effect", "reconcile_effect"}:
                findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", target.attr))
            if target.attr in INNER_VALIDATED_METHODS and not inner_allowed:
                findings.append(BoundaryFinding(str(path), target.lineno, "INNER_EXECUTOR_BYPASS", target.attr))
            if target.attr == "execute":
                if isinstance(receiver, ast.Name) and receiver.id in durable_engine_receivers:
                    findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", "executor.execute"))
                if isinstance(receiver, ast.Name) and receiver.id == "DurableExecutionEngine":
                    findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", "DurableExecutionEngine.execute"))
            if target.attr == "handler" and isinstance(receiver, ast.Name):
                findings.append(BoundaryFinding(str(path), target.lineno, "DIRECT_HANDLER_BYPASS", f"{receiver.id}.handler(...)"))
        return findings

    @staticmethod
    def _raw_api_is_denied() -> bool:
        engine = object.__new__(DurableExecutionEngine)
        fabric = ToolFabric()
        probes = (
            (engine, "execute", (None, "MISSION", lambda _: None), {}),
            (engine, "execute_effect", (None, "MISSION", None), {"provider_name": "probe", "operation": "probe", "payload": None}),
            (engine, "reconcile_effect", (None, "MISSION", None), {"provider_name": "probe", "operation": "probe", "payload": None}),
            (fabric, "execute_autonomous", ("probe",), {}),
            (fabric, "execute_approved", ("APPROVAL", "probe"), {}),
        )
        for obj, method, args, kwargs in probes:
            try:
                getattr(obj, method)(*args, **kwargs)
            except PermissionError:
                continue
            except Exception:
                return False
            return False
        return True


__all__ = ["BoundaryFinding", "BoundaryAuditReport", "ExecutionBoundaryAuditor"]
