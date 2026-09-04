"""Persistence invariants for SQLite-backed stores.

DurableStore(":memory:") used to write its schema into a connection it dropped
and then answer every query from a fresh, empty database. Nothing raised: reads
came back empty, which a durable boundary reads as "no prior execution, no prior
approval, no prior idempotency record" -- the fail-open direction.
"""
import ast
from pathlib import Path

import pytest

from singular.approval_binding import ApprovalBindingStore
from singular.autopilot import Autonomy, DelegationContract
from singular.decision_attestation import DecisionAttestationStore
from singular.durable import DurableStore
from singular.improvement_registry import ImprovementRegistry
from singular.mission_runtime import DurableMissionRuntime
from singular.sqlite_support import SqliteLocation, is_shared_memory_target

PACKAGE = Path(__file__).resolve().parents[1] / "singular"


def _contract(mission_id: str = "MIS-MEM") -> DelegationContract:
    return DelegationContract(mission_id, "objective", "expected", autonomy=Autonomy.EXECUTE_REVERSIBLE)


def test_in_memory_store_survives_across_connections():
    store = DurableStore(":memory:")
    store.save_mission(_contract())
    assert store.load_mission("MIS-MEM").mission_id == "MIS-MEM"


def test_in_memory_idempotency_is_not_silently_empty():
    """The dangerous read: an absent record means "never executed"."""
    store = DurableStore(":memory:")
    key = store.idempotency_key("execute", "MIS-MEM", "ACT-1")
    store.put_idempotent(key, {"done": True}, fingerprint="fp")
    assert store.get_idempotency_fingerprint(key) == "fp"


def test_derived_stores_join_the_same_in_memory_database():
    store = DurableStore(":memory:")
    runtime = DurableMissionRuntime(store)
    assert runtime.approval_bindings.path == store.path
    assert runtime.approval_integrity.path == store.path
    assert ApprovalBindingStore(store.path).path == store.path


def test_separate_in_memory_stores_stay_isolated():
    first = DurableStore(":memory:")
    first.save_mission(_contract("MIS-A"))
    second = DurableStore(":memory:")
    assert second.load_mission("MIS-A") is None


def test_memory_uri_is_never_created_as_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    location = SqliteLocation("file:handmade_probe?mode=memory&cache=shared")
    assert location.uri is True
    with location.connect() as conn:
        conn.execute("CREATE TABLE t(x)")
    assert not any(entry.name.startswith("file:") for entry in tmp_path.iterdir())


def test_file_backed_store_still_persists_across_instances(tmp_path):
    path = tmp_path / "singular.db"
    DurableStore(path).save_mission(_contract("MIS-FILE"))
    assert DurableStore(path).load_mission("MIS-FILE").mission_id == "MIS-FILE"


def test_attestation_and_improvement_stores_accept_memory():
    assert DecisionAttestationStore(":memory:").get("absent") is None
    registry = ImprovementRegistry(":memory:")
    assert registry.active("target") is None


def test_is_shared_memory_target_recognises_foreign_uris():
    assert is_shared_memory_target("file:whatever?mode=memory&cache=shared")
    assert not is_shared_memory_target("/var/lib/singular.db")
    assert not is_shared_memory_target(":memory:")


def test_no_module_opens_sqlite_directly():
    """One resolution point, or ":memory:" silently regresses in the next store."""
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "sqlite_support.py" or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "connect" and isinstance(node.func.value, ast.Name) and node.func.value.id == "sqlite3":
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert not offenders, (
        "every store must resolve its database through SqliteLocation:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("factory", [DurableStore, DecisionAttestationStore, ImprovementRegistry])
def test_stores_expose_a_resolved_path_rather_than_the_raw_memory_marker(factory):
    store = factory(":memory:")
    assert str(store.path) != ":memory:"
    assert is_shared_memory_target(str(store.path))
