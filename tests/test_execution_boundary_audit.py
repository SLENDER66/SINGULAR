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


def test_boundary_auditor_detects_legacy_execution_ledger(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "from singular.durable_execution import DurableExecutionLedger\n"
        "ledger = DurableExecutionLedger(store)\n"
        "ledger.record(result)\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "NON_AUTHORITATIVE_EXECUTION_LEDGER" for f in report.findings)


def test_boundary_auditor_detects_legacy_execution_ledger_alias(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "from singular.durable_execution import DurableExecutionLedger as Ledger\n"
        "ledger = Ledger(store)\n"
        "alias = ledger\n"
        "alias.record_intent(intent, status=status, success=True)\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "NON_AUTHORITATIVE_EXECUTION_LEDGER" for f in report.findings)


def test_boundary_auditor_scans_nested_python_modules(tmp_path: Path):
    package = tmp_path / "singular"
    nested = package / "nested"
    nested.mkdir(parents=True)
    (nested / "unsafe.py").write_text("agent.handler(action)\n", encoding="utf-8")

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "DIRECT_HANDLER_BYPASS" and f.path.endswith("nested/unsafe.py") for f in report.findings)
    assert report.checked_files == 1


def _package(tmp_path: Path, source: str) -> Path:
    package = tmp_path / "singular"
    package.mkdir(exist_ok=True)
    (package / "unsafe.py").write_text(source, encoding="utf-8")
    return package


def test_validated_wrapper_call_is_not_a_bypass(tmp_path: Path):
    """ValidatedExecutionBoundary.execute_effect shares the raw engine's method name.

    Matching on the name alone reported a bypass for every safe wrapper call and
    made the audit permanently dirty, so the CI gate could never pass.

    Written as a boundary module: whether a module should hold the front door at
    all is the question AUTHORITY_IMPORT_LEAK answers, not this one.
    """
    package = tmp_path / "singular"
    package.mkdir()
    (package / "control_plane.py").write_text(
        "from singular.execution import DurableExecutionEngine\n"
        "from singular.validated_execution import ValidatedExecutionBoundary\n"
        "class Service:\n"
        "    def __init__(self, executor: DurableExecutionEngine) -> None:\n"
        "        self.boundary = ValidatedExecutionBoundary(executor)\n"
        "    def run(self, decision, action_id, provider):\n"
        "        return self.boundary.execute_effect(decision, action_id, provider)\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert not report.findings, report.findings


def test_boundary_auditor_detects_annotated_executor_parameter_bypass(tmp_path: Path):
    """An engine injected through an annotated parameter is still the raw engine."""
    package = _package(
        tmp_path,
        "from singular.execution import DurableExecutionEngine\n"
        "def run(executor: DurableExecutionEngine, action, mission_id, provider):\n"
        "    return executor.execute_effect(action, mission_id, provider)\n",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "RAW_ENGINE_BYPASS" for f in report.findings), report.findings


def test_boundary_auditor_detects_executor_stored_on_self(tmp_path: Path):
    package = _package(
        tmp_path,
        "from singular.execution import DurableExecutionEngine\n"
        "class Runner:\n"
        "    def __init__(self, runtime) -> None:\n"
        "        self.engine = DurableExecutionEngine(runtime)\n"
        "    def go(self, action, mission_id, handler):\n"
        "        return self.engine.execute(action, mission_id, handler)\n",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "RAW_ENGINE_BYPASS" for f in report.findings), report.findings


def test_safe_receiver_later_rebound_to_the_executor_is_still_a_bypass(tmp_path: Path):
    """Laundering the engine through a name that once held a safe wrapper."""
    package = _package(
        tmp_path,
        "from singular.execution import DurableExecutionEngine\n"
        "from singular.validated_execution import ValidatedExecutionBoundary\n"
        "class Runner:\n"
        "    def __init__(self, runtime) -> None:\n"
        "        self.boundary = ValidatedExecutionBoundary(runtime)\n"
        "        engine = DurableExecutionEngine(runtime)\n"
        "        self.boundary = engine\n"
        "    def go(self, action, mission_id, handler):\n"
        "        return self.boundary.execute(action, mission_id, handler)\n",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "RAW_ENGINE_BYPASS" for f in report.findings), report.findings


def test_unresolved_receiver_is_reported_when_the_engine_is_in_scope(tmp_path: Path):
    """Relaxing the name-only rule must not become blanket trust."""
    package = _package(
        tmp_path,
        "from singular.execution import DurableExecutionEngine\n"
        "def run(action, mission_id, provider):\n"
        "    return registry[key].execute_effect(action, mission_id, provider)\n",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "UNRESOLVED_RAW_EXECUTION_RECEIVER" for f in report.findings), report.findings


def test_sqlite_execute_is_not_reported_when_no_engine_is_in_scope(tmp_path: Path):
    """`conn.execute(...)` is the dominant call in this codebase; it is not execution."""
    package = _package(
        tmp_path,
        "import sqlite3\n"
        "def load(path, key):\n"
        "    conn = sqlite3.connect(path)\n"
        "    return conn.execute('SELECT 1 FROM t WHERE k=?', (key,)).fetchone()\n",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert not [f for f in report.findings if f.path.endswith("unsafe.py")], report.findings


# --- authority isolation -----------------------------------------------------

def test_an_advisory_module_cannot_import_the_execution_stack(tmp_path: Path):
    """Orchestration and learning propose; importing the execution stack is how that stops being true."""
    package = tmp_path / "singular"
    package.mkdir()
    (package / "planner.py").write_text("from .execution import DurableExecutionEngine\n", encoding="utf-8")

    report = ExecutionBoundaryAuditor(package).audit()
    leaks = [f for f in report.findings if f.rule == "AUTHORITY_IMPORT_LEAK"]
    assert [f.detail for f in leaks] == ["execution"]
    assert leaks[0].path.endswith("planner.py")


def test_an_absolute_import_of_the_execution_stack_is_covered(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "planner.py").write_text("import singular.validated_execution\n", encoding="utf-8")

    report = ExecutionBoundaryAuditor(package).audit()
    assert any(f.rule == "AUTHORITY_IMPORT_LEAK" for f in report.findings)


def test_a_boundary_module_may_import_the_execution_stack(tmp_path: Path):
    package = tmp_path / "singular"
    package.mkdir()
    (package / "control_plane.py").write_text("from .execution import DurableExecutionEngine\n", encoding="utf-8")

    report = ExecutionBoundaryAuditor(package).audit()
    assert not [f for f in report.findings if f.rule == "AUTHORITY_IMPORT_LEAK"]


def test_reading_a_decision_is_not_reaching_for_execution(tmp_path: Path):
    """Learning has to verify what really happened; neither of these can cause an effect."""
    package = tmp_path / "singular"
    package.mkdir()
    (package / "learning.py").write_text(
        "from .validated_trajectory_decision import ValidatedTrajectoryDecision\n"
        "from .decision_attestation import DecisionAttestationStore\n",
        encoding="utf-8",
    )

    report = ExecutionBoundaryAuditor(package).audit()
    assert not [f for f in report.findings if f.rule == "AUTHORITY_IMPORT_LEAK"]
