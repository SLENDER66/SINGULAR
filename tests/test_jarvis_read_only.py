from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from singular.autopilot import ActionRequest
from singular.jarvis.read_only import make_read_only_repository_tool, verify_read_only_result


def _action(name: str) -> ActionRequest:
    return ActionRequest(
        name=name,
        description="Read-only repository inspection",
        impact=2,
        risk=0,
        reversibility=10,
        contract_id="MIS-READ",
    )


def test_read_only_tool_reads_only_bounded_relative_files(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    capability, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_read_only")

    result = handler(_action("read:README.md"))

    assert capability == "cap_test_read_only"
    assert result == {
        "path": "README.md",
        "bytes": 5,
        "sha256": hashlib.sha256(b"hello").hexdigest(),
        "text": "hello",
    }


def test_read_only_result_is_independently_verified(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    _, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_read_only_verify")
    action = _action("read:README.md")
    result = handler(action)

    assert verify_read_only_result(tmp_path, action, result)

    tampered = dict(result)
    tampered["sha256"] = "0" * 64
    assert not verify_read_only_result(tmp_path, action, tampered)

    tampered = dict(result)
    tampered["path"] = "other.txt"
    assert not verify_read_only_result(tmp_path, action, tampered)


def test_read_only_tool_rejects_absolute_and_escape_paths(tmp_path: Path):
    _, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_read_only_escape")

    with pytest.raises(PermissionError):
        handler(_action("read:../secret"))
    with pytest.raises(PermissionError):
        handler(_action("read:/etc/passwd"))


def test_read_only_tool_rejects_wrong_action_shape(tmp_path: Path):
    _, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_read_only_shape")

    with pytest.raises(ValueError):
        handler(_action("inspect"))


def test_read_only_tool_enforces_size_limit(tmp_path: Path):
    (tmp_path / "large.txt").write_text("123456", encoding="utf-8")
    _, handler = make_read_only_repository_tool(
        tmp_path,
        max_bytes=5,
        capability_id="cap_test_read_only_size",
    )

    with pytest.raises(ValueError, match="exceeds configured read limit"):
        handler(_action("read:large.txt"))


def test_independent_verifier_rejects_changed_file(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    _, handler = make_read_only_repository_tool(tmp_path, capability_id="cap_test_read_only_changed")
    action = _action("read:README.md")
    result = handler(action)
    (tmp_path / "README.md").write_text("changed", encoding="utf-8")

    assert not verify_read_only_result(tmp_path, action, result)
