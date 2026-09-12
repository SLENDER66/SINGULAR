"""SINGULAR-native adversarial security assessment.

This module is intentionally independent of third-party pentest projects. It
reimplements only the useful security-assessment ideas SINGULAR needs: bounded
attack planning, source-aware triage, deterministic probes, evidence-backed
findings, scan depth, and fail-closed CI reporting.

It is a security tester, never an authority. It cannot authorize or execute
SINGULAR actions on the target.
"""
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from .adversarial import AdversarialEngine
from .execution_boundary_audit import ExecutionBoundaryAuditor


class ScanMode(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass(frozen=True)
class SecurityFinding:
    finding_id: str
    severity: FindingSeverity
    rule: str
    path: str
    line: int
    title: str
    evidence: str
    validated: bool
    remediation: str


@dataclass(frozen=True)
class SecurityReport:
    mode: ScanMode
    findings: tuple[SecurityFinding, ...]
    files_scanned: int
    probes_run: int

    @property
    def failures(self) -> tuple[SecurityFinding, ...]:
        """Return only high-impact findings whose exploitability was validated.

        Static source rules are deliberately triage signals. Treating an
        ``eval(...)`` observation as a validated vulnerability would collapse
        OBSERVED and VALIDATED, creating both false positives and a false sense
        that the scanner had demonstrated exploitability. Dynamic adversarial
        probes and the execution-boundary audit provide the validation evidence.
        """
        return tuple(
            f
            for f in self.findings
            if f.validated and f.severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH}
        )

    @property
    def clean(self) -> bool:
        return not self.failures

    @property
    def observed_high_risk(self) -> tuple[SecurityFinding, ...]:
        """High-impact observations that still require validation."""
        return tuple(
            f
            for f in self.findings
            if not f.validated and f.severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "clean": self.clean,
            "files_scanned": self.files_scanned,
            "probes_run": self.probes_run,
            "findings": [
                {
                    "id": f.finding_id,
                    "severity": f.severity.value,
                    "rule": f.rule,
                    "path": f.path,
                    "line": f.line,
                    "title": f.title,
                    "evidence": f.evidence,
                    "validated": f.validated,
                    "remediation": f.remediation,
                }
                for f in self.findings
            ],
        }


class SingularSecurityAssessment:
    """White-box red-team engine dedicated to SINGULAR's threat model."""

    _SKIP_PARTS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}
    _SEVERITIES = {"critical": FindingSeverity.CRITICAL, "high": FindingSeverity.HIGH, "medium": FindingSeverity.MEDIUM}

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(__file__).resolve().parent).resolve()

    def scan(self, mode: ScanMode = ScanMode.STANDARD) -> SecurityReport:
        files = tuple(self._python_files())
        findings: list[SecurityFinding] = []
        if mode in {ScanMode.STANDARD, ScanMode.DEEP}:
            for path in files:
                findings.extend(self._source_rules(path, mode))

        # Existing SINGULAR adversarial controls are the dynamic/behavioral core.
        # Their findings are already validated by their own isolated probes.
        adversarial = AdversarialEngine.full_suite()
        findings.extend(self._adversarial_findings(adversarial.findings))

        boundary = ExecutionBoundaryAuditor(self.root).audit()
        findings.extend(self._boundary_findings(boundary.findings))
        if not boundary.raw_execution_is_denied:
            findings.append(
                SecurityFinding(
                    "RT-AUTH-000",
                    FindingSeverity.CRITICAL,
                    "RAW_API_NOT_DENY_BY_DEFAULT",
                    "runtime",
                    0,
                    "Raw execution API is not fail-closed",
                    "The existing execution-boundary probe did not receive PermissionError.",
                    True,
                    "Restore deny-by-default raw execution entry points before allowing effects.",
                )
            )

        return SecurityReport(mode, tuple(self._deduplicate(findings)), len(files), len(adversarial.findings) + len(boundary.findings) + 1)

    def _python_files(self) -> Iterable[Path]:
        for path in sorted(self.root.rglob("*.py")):
            if any(part in self._SKIP_PARTS for part in path.parts):
                continue
            yield path

    def _source_rules(self, path: Path, mode: ScanMode) -> list[SecurityFinding]:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            return [SecurityFinding("RT-SOURCE-001", FindingSeverity.HIGH, "PARSE_ERROR", self._relative(path), 1, "Source cannot be parsed", str(exc), True, "Fix the parse error before trusting security analysis.")]

        findings: list[SecurityFinding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                findings.extend(self._call_rules(path, node, mode))
            elif isinstance(node, ast.ImportFrom):
                findings.extend(self._import_rules(path, node, mode))
        return findings

    def _call_rules(self, path: Path, node: ast.Call, mode: ScanMode) -> list[SecurityFinding]:
        name = self._call_name(node)
        relative = self._relative(path)
        findings: list[SecurityFinding] = []
        if name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
            findings.append(SecurityFinding("RT-CODE-001", FindingSeverity.HIGH, "DYNAMIC_CODE_EXECUTION", relative, node.lineno, "Dynamic code execution", f"{name}(...)", False, "Replace dynamic evaluation with a bounded parser or explicit dispatch."))
        if name in {"os.system", "os.popen"}:
            findings.append(SecurityFinding("RT-CMD-001", FindingSeverity.HIGH, "SHELL_EXECUTION", relative, node.lineno, "Shell execution primitive", f"{name}(...) can cross the process boundary", False, "Use a fixed executable and argument vector; never pass attacker-controlled shell syntax."))
        if name.startswith("subprocess."):
            shell_true = any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords)
            if shell_true:
                findings.append(SecurityFinding("RT-CMD-002", FindingSeverity.CRITICAL, "SHELL_TRUE", relative, node.lineno, "Subprocess uses shell=True", "shell=True creates a command-interpreter boundary", False, "Use shell=False with a structured argv and strict executable allowlist."))
        if name in {"pickle.load", "pickle.loads", "dill.load", "dill.loads"}:
            findings.append(SecurityFinding("RT-DATA-001", FindingSeverity.HIGH, "UNSAFE_DESERIALIZATION", relative, node.lineno, "Unsafe object deserialization", f"{name}(...)", False, "Use a safe data format with explicit schemas and no executable object reconstruction."))
        if name in {"yaml.load", "yaml.unsafe_load", "yaml.full_load"}:
            safe_loader = any(keyword.arg == "Loader" and isinstance(keyword.value, ast.Attribute) and keyword.value.attr == "SafeLoader" for keyword in node.keywords)
            if not safe_loader:
                findings.append(SecurityFinding("RT-DATA-002", FindingSeverity.HIGH, "UNSAFE_YAML_LOAD", relative, node.lineno, "YAML loader may construct objects", f"{name}(...) without SafeLoader", False, "Use yaml.safe_load or an explicit SafeLoader."))
        return findings

    def _import_rules(self, path: Path, node: ast.ImportFrom, mode: ScanMode) -> list[SecurityFinding]:
        if mode is not ScanMode.DEEP:
            return []
        module = node.module or ""
        if module in {"pickle", "dill"}:
            return [SecurityFinding("RT-DATA-003", FindingSeverity.MEDIUM, "UNSAFE_SERIALIZATION_IMPORT", self._relative(path), node.lineno, "Unsafe deserialization library imported", module, False, "Prefer a schema-bound data format unless executable object reconstruction is strictly required.")]
        return []

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        value: ast.AST = node.func
        parts: list[str] = []
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))

    def _adversarial_findings(self, findings: Iterable[object]) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for finding in findings:
            passed = bool(getattr(finding, "passed"))
            if passed:
                continue
            severity = getattr(finding, "severity").value
            result.append(SecurityFinding(
                f"RT-{getattr(finding, 'attack_id')}",
                self._SEVERITIES.get(severity.lower(), FindingSeverity.MEDIUM),
                "VALIDATED_ADVERSARIAL_CONTROL",
                "singular/adversarial.py",
                0,
                str(getattr(finding, "subject")),
                str(getattr(finding, "evidence")),
                True,
                str(getattr(finding, "remediation")),
            ))
        return result

    def _boundary_findings(self, findings: Iterable[object]) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for finding in findings:
            rule = str(getattr(finding, "rule"))
            severity = FindingSeverity.CRITICAL if rule in {"RAW_ENGINE_BYPASS", "RAW_TOOL_BYPASS", "INNER_EXECUTOR_BYPASS", "AUTHORITY_IMPORT_LEAK", "DIRECT_HANDLER_BYPASS"} else FindingSeverity.HIGH
            result.append(SecurityFinding(
                f"RT-BOUNDARY-{rule}", severity, rule, str(getattr(finding, "path")), int(getattr(finding, "line")), rule, str(getattr(finding, "detail")), True, "Restore the single governed execution path and rerun the boundary audit."))
        return result

    @staticmethod
    def _deduplicate(findings: Iterable[SecurityFinding]) -> list[SecurityFinding]:
        seen: set[tuple[str, str, int]] = set()
        result: list[SecurityFinding] = []
        for finding in findings:
            key = (finding.rule, finding.path, finding.line)
            if key in seen:
                continue
            seen.add(key)
            result.append(finding)
        return result

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root.parent).as_posix()
        except ValueError:
            return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="singular-redteam", description="SINGULAR-native adversarial security assessment")
    parser.add_argument("--mode", choices=[mode.value for mode in ScanMode], default=ScanMode.QUICK.value)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    report = SingularSecurityAssessment(args.root).scan(ScanMode(args.mode))
    if args.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(f"SINGULAR RED TEAM mode={report.mode.value} files={report.files_scanned} probes={report.probes_run}")
        for finding in report.findings:
            print(f"{finding.severity.value:8} {finding.rule:32} {finding.path}:{finding.line} {finding.title}")
        print(f"RESULT clean={report.clean} findings={len(report.findings)} observed_high_risk={len(report.observed_high_risk)}")
    return 0 if report.clean else 1


__all__ = ["FindingSeverity", "ScanMode", "SecurityFinding", "SecurityReport", "SingularSecurityAssessment", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
