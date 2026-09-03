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


def test_boundary_auditor_detects_direct_inner_executor_bypass(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "from singular.execution import DurableExecutionEngine\n"
        "executor = DurableExecutionEngine(runtime)\n"
        "executor.execute_validated(decision, handler)\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "INNER_EXECUTOR_BYPASS" for f in report.findings)


def test_boundary_auditor_detects_executor_alias_bypass(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "from singular.execution import DurableExecutionEngine as Engine\n"
        "executor = Engine(runtime)\n"
        "runner = executor\n"
        "runner.execute(action, mission_id, handler)\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "RAW_ENGINE_BYPASS" for f in report.findings)


def test_boundary_auditor_detects_qualified_executor_bypass(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "import singular.execution as execution\n"
        "executor = execution.DurableExecutionEngine(runtime)\n"
        "executor.execute(action, mission_id, handler)\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "RAW_ENGINE_BYPASS" for f in report.findings)
