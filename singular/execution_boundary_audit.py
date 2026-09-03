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
    """Detect production execution bypasses and verify raw API denial.

    The static pass is deliberately conservative: it tracks imports, direct
    executor construction and simple assignment aliases so that a trivial rename
    cannot hide an execution bypass. It is a guardrail, not a formal proof.
    """

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
            findings.append(
                BoundaryFinding(
                    "runtime",
                    0,
                    "RAW_API_NOT_DENY_BY_DEFAULT",
                    "A public raw execution entry point did not raise PermissionError.",
                )
            )
        return BoundaryAuditReport(tuple(findings), checked, raw_denied)

    @staticmethod
    def _scan(path: Path, tree: ast.AST) -> list[BoundaryFinding]:
        findings: list[BoundaryFinding] = []
        executor_type_names = {"DurableExecutionEngine"}
        executor_receivers: set[str] = set()

        # Resolve the common import spellings used by production code.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == ".execution":
                for alias in node.names:
                    if alias.name == "DurableExecutionEngine":
                        executor_type_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.endswith("execution"):
                        executor_type_names.add(alias.asname or alias.name.split(".")[-1])

        def is_executor_constructor(expr: ast.AST) -> bool:
            if isinstance(expr, ast.Name):
                return expr.id in executor_type_names
            if isinstance(expr, ast.Attribute):
                return expr.attr == "DurableExecutionEngine"
            return False

        # Track direct constructions and one-step aliases (runner = executor).
        changed = True
        while changed:
            changed = False
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    value = node.value
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if value is not None and is_executor_constructor(value.func if isinstance(value, ast.Call) else value):
                        for target in targets:
                            if isinstance(target, ast.Name) and target.id not in executor_receivers:
                                executor_receivers.add(target.id)
                                changed = True
                    elif isinstance(value, ast.Name) and value.id in executor_receivers:
                        for target in targets:
                            if isinstance(target, ast.Name) and target.id not in executor_receivers:
                                executor_receivers.add(target.id)
                                changed = True

        inner_allowed = path.name in INNER_ALLOWED_MODULES
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            target = node.func
            receiver = target.value

            if target.attr in RAW_TOOL_METHODS:
                findings.append(BoundaryFinding(str(path), target.lineno, "RAW_TOOL_BYPASS", target.attr))

            if target.attr in {"execute_effect", "reconcile_effect"}:
                # These names are execution primitives; any production call outside
                # the definition/approved adapter is suspicious and must be reviewed.
                findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", target.attr))

            if target.attr in INNER_VALIDATED_METHODS and not inner_allowed:
                findings.append(BoundaryFinding(str(path), target.lineno, "INNER_EXECUTOR_BYPASS", target.attr))

            if target.attr == "execute":
                if isinstance(receiver, ast.Name) and receiver.id in executor_receivers:
                    findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", "executor.execute"))
                if isinstance(receiver, ast.Name) and receiver.id in executor_type_names:
                    findings.append(BoundaryFinding(str(path), target.lineno, "RAW_ENGINE_BYPASS", "DurableExecutionEngine.execute"))
                if isinstance(receiver, ast.Attribute) and receiver.attr == "DurableExecutionEngine":
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
