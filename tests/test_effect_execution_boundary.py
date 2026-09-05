import pytest

from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.effects import EffectRequest, ExternalEffectCoordinator, ProviderResult


class CountingProvider:
    def __init__(self):
        self.execute_calls = 0
        self.reconcile_calls = 0

    def execute(self, request, idempotency_key):
        self.execute_calls += 1
        return ProviderResult("COMPLETED", {"ok": True})

    def reconcile(self, request, idempotency_key):
        self.reconcile_calls += 1
        return ProviderResult("COMPLETED", {"remote": True})


def _store_with_execution(tmp_path, status):
    store = DurableStore(tmp_path / "singular.db")
    store.save_mission(
        DelegationContract(
            mission_id="MIS-EFFECT-BOUNDARY",
            objective="test",
            expected_result="done",
        )
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-EFFECT-BOUNDARY'"
        )
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-boundary", "MIS-EFFECT-BOUNDARY", "ACT-1", status),
        )
    return store


def _request():
    return EffectRequest(
        execution_key="exec-boundary",
        provider="provider",
        operation="write",
        payload={"value": 1},
        action_fingerprint="action-fp",
    )


def test_recovery_required_execution_cannot_reexecute_external_effect(tmp_path):
    store = _store_with_execution(tmp_path, "RECOVERY_REQUIRED")
    coordinator = ExternalEffectCoordinator(store)
    provider = CountingProvider()

    with pytest.raises(RuntimeError, match="réconciliation explicite"):
        coordinator.execute(_request(), provider)

    assert provider.execute_calls == 0


def test_completed_execution_cannot_reexecute_external_effect(tmp_path):
    store = _store_with_execution(tmp_path, "COMPLETED")
    coordinator = ExternalEffectCoordinator(store)
    provider = CountingProvider()

    with pytest.raises(RuntimeError, match="état COMPLETED"):
        coordinator.execute(_request(), provider)

    assert provider.execute_calls == 0


def test_missing_execution_cannot_create_external_effect(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    coordinator = ExternalEffectCoordinator(store)
    provider = CountingProvider()

    with pytest.raises(KeyError):
        coordinator.execute(_request(), provider)

    assert provider.execute_calls == 0


def test_running_execution_cannot_reconcile_external_effect(tmp_path):
    store = _store_with_execution(tmp_path, "RUNNING")
    coordinator = ExternalEffectCoordinator(store)
    request = _request()
    coordinator.prepare(request)
    provider = CountingProvider()

    with pytest.raises(RuntimeError, match="RECOVERY_REQUIRED"):
        coordinator.reconcile(request, provider)

    assert provider.reconcile_calls == 0


def test_an_effect_must_name_the_action_it_belongs_to():
    """A row without it is EFFECT-ACTION-BINDING for ever, and the boundary stays shut."""
    import pytest

    with pytest.raises(ValueError, match="doit nommer l'action"):
        EffectRequest(execution_key="exec", provider="p", operation="write", payload={}, action_fingerprint="")


def test_the_coordinator_does_not_declare_the_table_a_second_time(tmp_path):
    """Two definitions of external_effects disagreed about action_fingerprint.

    The store makes it NOT NULL DEFAULT '', the coordinator made it nullable;
    whichever ran first decided whether a missing action identity could even be
    written. The store owns the database.
    """
    import sqlite3

    from singular.durable import DurableStore
    from singular.effects import ExternalEffectCoordinator

    store = DurableStore(tmp_path / "owned.db")
    ExternalEffectCoordinator(store)
    with store._connect() as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(external_effects)")}
    assert columns["action_fingerprint"][3] == 1  # NOT NULL
    assert not hasattr(ExternalEffectCoordinator, "_init_schema")


def test_a_database_written_before_action_fingerprint_is_refused_at_open(tmp_path):
    """Adding the column fills old rows with '', which shuts the boundary for good."""
    import sqlite3

    import pytest

    from singular.durable import DurableStore

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE external_effects (
            provider_idempotency_key TEXT PRIMARY KEY, execution_key TEXT NOT NULL, provider TEXT NOT NULL,
            operation TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, status TEXT NOT NULL,
            result TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO external_effects VALUES('pk','exec','provider','write','pf','COMPLETED',NULL,NULL,'t','t');
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="migrate them explicitly"):
        DurableStore(path)


def test_an_empty_pre_migration_database_still_opens(tmp_path):
    import sqlite3

    from singular.durable import DurableStore

    path = tmp_path / "empty-legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE external_effects (
            provider_idempotency_key TEXT PRIMARY KEY, execution_key TEXT NOT NULL, provider TEXT NOT NULL,
            operation TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, status TEXT NOT NULL,
            result TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    store = DurableStore(path)
    with store._connect() as conn:
        assert "action_fingerprint" in {row[1] for row in conn.execute("PRAGMA table_info(external_effects)")}
