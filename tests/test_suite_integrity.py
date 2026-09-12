"""Invariants the test suite itself must satisfy.

A test suite that cannot be collected proves nothing. These tests guard the
import topology that makes every other test in this repository meaningful.
"""
import ast
import sys
from collections import defaultdict
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _test_modules() -> list[Path]:
    return sorted(TESTS_DIR.glob("test_*.py"))


def test_tests_directory_is_an_importable_package():
    """Without __init__.py, `from tests.test_x import ...` executes test_x twice.

    Double execution duplicates module-level side effects (execution-capability
    registration in particular) and interrupts collection of the whole suite.
    """
    assert (TESTS_DIR / "__init__.py").is_file()


def test_cross_module_test_imports_use_the_package_name():
    """A bare `from test_x import ...` binds a second copy of the same file.

    Both spellings resolve, but to two distinct module objects holding two
    distinct sets of functions, so identity-based registries see a conflict.
    """
    violations = []
    for path in _test_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module and node.module.startswith("test_"):
                    violations.append(f"{path.name}:{node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("test_"):
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
    assert not violations, (
        "test modules must be imported as `tests.<module>`, never bare:\n" + "\n".join(violations)
    )


def test_no_test_module_is_loaded_twice_under_different_names():
    """Detect an actual double import at runtime, not only in the source."""
    by_file: dict[str, list[str]] = defaultdict(list)
    for name, module in list(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if origin is None:
            continue
        resolved = Path(origin).resolve()
        if resolved.parent == TESTS_DIR and resolved.name.startswith("test_"):
            by_file[str(resolved)].append(name)
    duplicated = {path: names for path, names in by_file.items() if len(names) > 1}
    assert not duplicated, f"test modules executed more than once: {duplicated}"
