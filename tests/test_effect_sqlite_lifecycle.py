from singular.durable import DurableStore
from singular.effects import ExternalEffectCoordinator


def test_effect_sqlite_connection_has_busy_timeout_and_foreign_keys(tmp_path):
    store = DurableStore(tmp_path / "singular.db")
    coordinator = ExternalEffectCoordinator(store)
    with coordinator._connect() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
