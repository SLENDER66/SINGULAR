import threading

import pytest

from singular.autopilot import DelegationContract
from singular.durable import DurableStore
from singular.effects import EffectInProgress, EffectRequest, ExternalEffectCoordinator, ProviderResult


class BlockingProvider:
    def __init__(self, entered: threading.Event, release: threading.Event):
        self.entered = entered
        self.release = release
        self.calls = 0

    def execute(self, request, idempotency_key):
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=5)
        return ProviderResult("COMPLETED", {"remote_id": "42"})

    def reconcile(self, request, idempotency_key):
        raise AssertionError("reconcile must not be called")


def test_only_one_worker_can_claim_an_external_effect(tmp_path):
    db = tmp_path / "singular.db"
    store = DurableStore(db)
    store.save_mission(DelegationContract(mission_id="MIS-CONC", objective="test", expected_result="done"))
    with store._connect() as conn:
        conn.execute("UPDATE mission_states SET status='RUNNING' WHERE mission_id='MIS-CONC'")
        conn.execute(
            "INSERT INTO executions(execution_key,mission_id,action_id,status,started_at) VALUES(?,?,?,?,datetime('now'))",
            ("exec-conc", "MIS-CONC", "ACT-1", "RUNNING"),
        )

    request = EffectRequest("exec-conc", "provider", "write", {"value": 1}, "action-fp")
    first_store = DurableStore(db)
    second_store = DurableStore(db)
    first = ExternalEffectCoordinator(first_store)
    second = ExternalEffectCoordinator(second_store)
    entered = threading.Event()
    release = threading.Event()
    provider = BlockingProvider(entered, release)
    errors = []
    results = []

    def run_first():
        try:
            results.append(first.execute(request, provider))
        except Exception as exc:
            errors.append(exc)

    def run_second():
        assert entered.wait(timeout=5)
        try:
            results.append(second.execute(request, provider))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=run_first)
    t2 = threading.Thread(target=run_second)
    t1.start()
    t2.start()
    t2.join(timeout=5)
    release.set()
    t1.join(timeout=5)

    assert provider.calls == 1
    assert any(isinstance(error, EffectInProgress) for error in errors)
    assert len([result for result in results if result.status == "COMPLETED"]) == 1
