from pathlib import Path

from singular.security_assessment import (
    FindingSeverity,
    ScanMode,
    SingularSecurityAssessment,
)


def test_quick_scan_runs_existing_adversarial_and_boundary_controls() -> None:
    report = SingularSecurityAssessment().scan(ScanMode.QUICK)
    assert report.clean, report.findings
    assert report.probes_run >= 1
    assert report.files_scanned >= 1


def test_source_rules_detect_dynamic_code_execution(tmp_path: Path) -> None:
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text("result = eval(user_input)\n", encoding="utf-8")

    report = SingularSecurityAssessment(package).scan(ScanMode.STANDARD)
    findings = [finding for finding in report.findings if finding.rule == "DYNAMIC_CODE_EXECUTION"]
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.HIGH
    assert findings[0].validated is False
    assert findings[0] in report.observed_high_risk
    assert findings[0] not in report.failures
    assert report.clean


def test_source_rules_detect_shell_true(tmp_path: Path) -> None:
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "import subprocess\nsubprocess.run(user_input, shell=True)\n",
        encoding="utf-8",
    )

    report = SingularSecurityAssessment(package).scan(ScanMode.STANDARD)
    findings = [f for f in report.findings if f.rule == "SHELL_TRUE"]
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.CRITICAL
    assert findings[0].validated is False
    assert findings[0] in report.observed_high_risk
    assert findings[0] not in report.failures


def test_source_rules_detect_unsafe_pickle(tmp_path: Path) -> None:
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text(
        "import pickle\nvalue = pickle.loads(payload)\n",
        encoding="utf-8",
    )

    report = SingularSecurityAssessment(package).scan(ScanMode.STANDARD)
    assert any(f.rule == "UNSAFE_DESERIALIZATION" for f in report.findings)


def test_deep_mode_adds_import_triage(tmp_path: Path) -> None:
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text("from pickle import loads\n", encoding="utf-8")

    standard = SingularSecurityAssessment(package).scan(ScanMode.STANDARD)
    deep = SingularSecurityAssessment(package).scan(ScanMode.DEEP)
    assert not any(f.rule == "UNSAFE_SERIALIZATION_IMPORT" for f in standard.findings)
    assert any(f.rule == "UNSAFE_SERIALIZATION_IMPORT" for f in deep.findings)


def test_findings_are_deduplicated(tmp_path: Path) -> None:
    package = tmp_path / "singular"
    package.mkdir()
    (package / "unsafe.py").write_text("eval(user_input)\n", encoding="utf-8")

    report = SingularSecurityAssessment(package).scan(ScanMode.STANDARD)
    matching = [f for f in report.findings if f.rule == "DYNAMIC_CODE_EXECUTION"]
    assert len(matching) == 1
