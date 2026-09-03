import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "singular"
DEFINING_MODULES = {"execution.py", "tool_fabric.py", "mission_autopilot.py", "empire.py"}
FORBIDDEN_METHODS = {"execute_approved", "execute_autonomous", "execute_effect", "reconcile_effect"}


def _production_python_files():
    return sorted(path for path in ROOT.rglob("*.py") if path.name not in DEFINING_MODULES)


def test_production_has_no_direct_raw_execution_api_calls():
    violations = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in FORBIDDEN_METHODS:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: .{node.func.attr}(...)")
            if node.func.attr == "execute" and isinstance(node.func.value, ast.Name) and node.func.value.id == "DurableExecutionEngine":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: DurableExecutionEngine.execute(...)")
    assert not violations, "raw execution APIs must never be called from production modules:\n" + "\n".join(violations)


def test_production_never_invokes_an_agent_handler_directly():
    violations = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "handler" and isinstance(node.func.value, ast.Name) and node.func.value.id == "agent":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: agent.handler(...)")
    assert not violations, "agent handlers must only be reached through the validated execution boundary:\n" + "\n".join(violations)
