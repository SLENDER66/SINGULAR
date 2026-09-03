from pathlib import Path

from singular.execution_boundary_audit import ExecutionBoundaryAuditor


def test_execution_boundary_audit_is_clean_for_current_package():
    report = ExecutionBoundaryAuditor().audit()
    assert report.raw_execution_is_denied is True
    assert report.clean, report.findings
    assert report.checked_files >= 1


def test_boundary_auditor_detects_direct_handler_bypass(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text("agent.handler(action)\n", encoding="utf-8")

    auditor = ExecutionBoundaryAuditor(package)
    report = auditor.audit()
    assert any(f.rule == "DIRECT_HANDLER_BYPASS" for f in report.findings)
