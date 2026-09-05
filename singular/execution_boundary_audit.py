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
LEGACY_LEDGER_METHODS = frozenset({"record", "record_intent"})
DEFINITION_MODULES = frozenset({"execution.py", "tool_fabric.py"})
INNER_ALLOWED_MODULES = frozenset({"validated_execution.py", "validated_decision_service.py"})

EXECUTOR_TYPE = "DurableExecutionEngine"
LEDGER_TYPE = "DurableExecutionLedger"
#: Wrappers that require a ValidatedTrajectoryDecision and expose methods whose
#: names collide with the raw engine API. A call on one of these is not a bypass.
SAFE_BOUNDARY_TYPES = frozenset({"ValidatedExecutionBoundary", "ValidatedDecisionService", "SingularControlPlane"})


@dataclass(frozen=True)
class BoundaryFinding:
    #: Always posix-separated, so a report reads the same on every platform and
    #: can be compared with one produced elsewhere.
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


class _ReceiverTypes:
    """Resolve which expressions in a module denote which boundary object.

    `execute`, `execute_effect` and `reconcile_effect` are method names shared by
    the raw `DurableExecutionEngine` and by the validated wrappers that guard it,
    so the method name alone cannot decide whether a call is a bypass. Only the
    receiver can. This tracks the receivers it can prove: local names and
    ``self.<attribute>`` bound from a constructor call, from an annotated
    parameter, or from another already-resolved binding.

    Unproven receivers are not silently trusted: `audit` reports them whenever the
    raw engine is in scope in the same module (see UNRESOLVED_RAW_EXECUTION_RECEIVER).
    An engine reaching a module through an unannotated parameter remains outside
    what this static pass can see; it is a guardrail, not a formal proof.
    """

    def __init__(self, tree: ast.AST) -> None:
        self.executor_types = {EXECUTOR_TYPE}
        self.ledger_types = {LEDGER_TYPE}
        self.safe_types = set(SAFE_BOUNDARY_TYPES)
        self.executor_imported = False
        self._collect_type_aliases(tree)
        self.executor: set[str] = set()
        self.ledger: set[str] = set()
        self.safe: set[str] = set()
        self._collect_bindings(tree)

    def _collect_type_aliases(self, tree: ast.AST) -> None:
        """Bind local aliases of the boundary types, from any import spelling."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.name == EXECUTOR_TYPE:
                        self.executor_types.add(local)
                        self.executor_imported = True
                    elif alias.name == LEDGER_TYPE:
                        self.ledger_types.add(local)
                    elif alias.name in SAFE_BOUNDARY_TYPES:
                        self.safe_types.add(local)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[-1]
                    if alias.name.endswith("execution"):
                        self.executor_types.add(local)
                        self.executor_imported = True
                    if alias.name.endswith("durable_execution"):
                        self.ledger_types.add(local)

    @staticmethod
    def key(expr: ast.AST | None) -> str | None:
        """A stable identity for a receiver expression, or None if untrackable."""
        if isinstance(expr, ast.Name):
            return f"name:{expr.id}"
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            return f"attr:{expr.value.id}.{expr.attr}"
        return None

    def _type_of_annotation(self, annotation: ast.AST | None) -> set[str]:
        """Type names mentioned by an annotation, unwrapping `X | None` and `Optional[X]`."""
        names: set[str] = set()
        if annotation is None:
            return names
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                annotation = ast.parse(annotation.value, mode="eval").body
            except SyntaxError:
                return names
        for node in ast.walk(annotation):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        return names

    def _bucket_for_types(self, names: set[str]) -> set[str] | None:
        if names & self.executor_types:
            return self.executor
        if names & self.ledger_types:
            return self.ledger
        if names & self.safe_types:
            return self.safe
        return None

    def _constructed_bucket(self, value: ast.AST | None) -> set[str] | None:
        """The bucket a right-hand side constructs, if it is a known constructor call."""
        if value is None:
            return None
        expr = value.func if isinstance(value, ast.Call) else value
        if isinstance(expr, ast.Name):
            return self._bucket_for_types({expr.id})
        if isinstance(expr, ast.Attribute):
            return self._bucket_for_types({expr.attr})
        return None

    def _collect_bindings(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = node.args
                for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
                    bucket = self._bucket_for_types(self._type_of_annotation(arg.annotation))
                    if bucket is not None:
                        bucket.add(f"name:{arg.arg}")

        changed = True
        while changed:
            changed = False
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                bucket = self._constructed_bucket(node.value)
                if bucket is None and isinstance(node, ast.AnnAssign):
                    bucket = self._bucket_for_types(self._type_of_annotation(node.annotation))
                if bucket is None:
                    source = self.key(node.value)
                    for candidate in (self.executor, self.ledger, self.safe):
                        if source is not None and source in candidate:
                            bucket = candidate
                            break
                if bucket is None:
                    continue
                for target in targets:
                    target_key = self.key(target)
                    if target_key is not None and target_key not in bucket:
                        bucket.add(target_key)
                        changed = True

    def is_executor_class(self, expr: ast.AST) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in self.executor_types
        if isinstance(expr, ast.Attribute):
            return expr.attr in self.executor_types or expr.attr == EXECUTOR_TYPE
        return False

    def is_ledger_class(self, expr: ast.AST) -> bool:
        if isinstance(expr, ast.Name):
            return expr.id in self.ledger_types
        if isinstance(expr, ast.Attribute):
            return expr.attr in self.ledger_types or expr.attr == LEDGER_TYPE
        return False

    @property
    def executor_in_scope(self) -> bool:
        """True when this module can actually reach a raw engine.

        Modules with no engine in scope call `execute` constantly (sqlite
        cursors, effect providers); reporting an unresolved receiver there
        would be pure noise.
        """
        return self.executor_imported or bool(self.executor)


class ExecutionBoundaryAuditor:
    """Detect production execution bypasses and verify raw API denial.

    The static pass is deliberately conservative: it tracks imports, direct
    executor construction, annotated parameters and simple assignment aliases so
    that a trivial rename cannot hide an execution bypass. It is a guardrail, not
    a formal proof.
    """

    def __init__(self, package_dir: Path | None = None) -> None:
        self.package_dir = package_dir or Path(__file__).resolve().parent

    def audit(self) -> BoundaryAuditReport:
        findings: list[BoundaryFinding] = []
        checked = 0
        for path in sorted(self.package_dir.rglob("*.py")):
            if any(part in {"__pycache__", ".git"} for part in path.parts):
                continue
            if path.name in DEFINITION_MODULES or path.name == "execution_boundary_audit.py":
                continue
            checked += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError) as exc:
                findings.append(BoundaryFinding(path.as_posix(), 1, "PARSE_ERROR", str(exc)))
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
        types = _ReceiverTypes(tree)
        inner_allowed = path.name in INNER_ALLOWED_MODULES

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            target = node.func
            receiver = target.value
            receiver_key = types.key(receiver)

            if target.attr in RAW_TOOL_METHODS:
                findings.append(BoundaryFinding(path.as_posix(), target.lineno, "RAW_TOOL_BYPASS", target.attr))

            if target.attr in INNER_VALIDATED_METHODS and not inner_allowed:
                findings.append(BoundaryFinding(path.as_posix(), target.lineno, "INNER_EXECUTOR_BYPASS", target.attr))

            if target.attr in RAW_METHODS:
                if receiver_key is not None and receiver_key in types.executor:
                    findings.append(BoundaryFinding(path.as_posix(), target.lineno, "RAW_ENGINE_BYPASS", f"{ast.unparse(receiver)}.{target.attr}"))
                elif types.is_executor_class(receiver):
                    findings.append(BoundaryFinding(path.as_posix(), target.lineno, "RAW_ENGINE_BYPASS", f"{EXECUTOR_TYPE}.{target.attr}"))
                elif receiver_key is not None and receiver_key in types.safe:
                    pass
                elif types.executor_in_scope:
                    findings.append(
                        BoundaryFinding(
                            path.as_posix(),
                            target.lineno,
                            "UNRESOLVED_RAW_EXECUTION_RECEIVER",
                            f"{ast.unparse(receiver)}.{target.attr} while {EXECUTOR_TYPE} is in scope",
                        )
                    )

            if target.attr == "handler" and isinstance(receiver, ast.Name):
                findings.append(BoundaryFinding(path.as_posix(), target.lineno, "DIRECT_HANDLER_BYPASS", f"{receiver.id}.handler(...)"))

            is_ledger_receiver = (receiver_key is not None and receiver_key in types.ledger) or types.is_ledger_class(receiver)
            if target.attr in LEGACY_LEDGER_METHODS and is_ledger_receiver:
                findings.append(
                    BoundaryFinding(
                        path.as_posix(),
                        target.lineno,
                        "NON_AUTHORITATIVE_EXECUTION_LEDGER",
                        f"legacy execution ledger: {target.attr}",
                    )
                )

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
