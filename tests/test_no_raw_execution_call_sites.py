"""No production module may call a raw execution API.

This used to reimplement its own AST scan, matching on method name alone. That
made it flag the validated wrappers whose methods legitimately share the raw
engine's names, so it reported bypasses that did not exist while a receiver-aware
bypass would still have slipped past it. There is now exactly one implementation
of the rule — ExecutionBoundaryAuditor — and this file asserts against it, so the
guard and the CI gate can never drift apart.
"""
from singular.execution_boundary_audit import ExecutionBoundaryAuditor

BYPASS_RULES = {
    "RAW_ENGINE_BYPASS",
    "RAW_TOOL_BYPASS",
    "INNER_EXECUTOR_BYPASS",
    "UNRESOLVED_RAW_EXECUTION_RECEIVER",
    "NON_AUTHORITATIVE_EXECUTION_LEDGER",
    "PARSE_ERROR",
}


def test_production_has_no_direct_raw_execution_api_calls():
    report = ExecutionBoundaryAuditor().audit()
    violations = [f"{f.path}:{f.line}: {f.rule} {f.detail}" for f in report.findings if f.rule in BYPASS_RULES]
    assert not violations, "raw execution APIs must never be called from production modules:\n" + "\n".join(violations)


def test_production_never_invokes_an_agent_handler_directly():
    report = ExecutionBoundaryAuditor().audit()
    violations = [f"{f.path}:{f.line}: {f.detail}" for f in report.findings if f.rule == "DIRECT_HANDLER_BYPASS"]
    assert not violations, "agent handlers must only be reached through the validated execution boundary:\n" + "\n".join(violations)


def test_raw_execution_entry_points_deny_by_default_at_runtime():
    """The static scan is worthless if the raw API stopped refusing at runtime."""
    assert ExecutionBoundaryAuditor().audit().raw_execution_is_denied is True
