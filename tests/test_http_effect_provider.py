"""The first effect that really leaves the process, against a real server.

Everything upstream of this file governs something. Until now there was nothing
to govern: EffectProvider was a Protocol with no implementation, and every
provider in the suite was a fake. These tests run the whole chain -- validated
decision, durable attestation, capability with an artifact identity, execution
lease, external effect, outcome -- against an HTTP server listening on a real
socket.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.effects import EffectRequest, EffectStatus, ExternalEffectCoordinator
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.providers.http_effect import (
    IDEMPOTENCY_HEADER,
    HttpEffectProvider,
    HttpProviderError,
)
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision

#: Every request the server saw, so a test can prove an effect was not repeated.
RECEIVED: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A003 - silence the default stderr logging
        pass

    def _record(self, body):
        RECEIVED.append({
            "path": self.path,
            "method": self.command,
            "idempotency_key": self.headers.get(IDEMPOTENCY_HEADER),
            "body": body,
        })

    def _respond(self, status: int, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"null")
        self._record(body)
        if self.path == "/slow":
            time.sleep(2.0)
        if self.path == "/broken":
            self._respond(500, {"error": "upstream unavailable"})
            return
        self._respond(200, {"accepted": True, "echo": body})

    def do_GET(self):  # noqa: N802
        self._record(None)
        key = self.headers.get(IDEMPOTENCY_HEADER)
        seen = any(entry["idempotency_key"] == key and entry["method"] == "POST" for entry in RECEIVED)
        self._respond(200, {"idempotency_key": key, "settled": seen})


@pytest.fixture
def server():
    RECEIVED.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _request(execution_key="execute-key", operation="notify", payload=None) -> EffectRequest:
    return EffectRequest(
        execution_key=execution_key,
        provider="http",
        operation=operation,
        payload={"message": "hello"} if payload is None else payload,
        action_fingerprint="action-fp",
    )


# --- provider behaviour ------------------------------------------------------

def test_successful_call_completes_and_returns_the_body(server):
    provider = HttpEffectProvider(f"{server}/notify")
    outcome = provider.execute(_request(), "idem-1")
    assert outcome.status == EffectStatus.COMPLETED.value
    assert outcome.result["status"] == 200
    assert outcome.result["body"]["echo"] == {"message": "hello"}


def test_the_idempotency_key_reaches_the_server(server):
    """The remote can only deduplicate if we tell it what to deduplicate on."""
    provider = HttpEffectProvider(f"{server}/notify")
    provider.execute(_request(), "idem-key-visible")
    assert RECEIVED[-1]["idempotency_key"] == "idem-key-visible"


def test_a_server_error_is_failed_not_unknown(server):
    """The server answered, so there is no ambiguity about whether it arrived."""
    provider = HttpEffectProvider(f"{server}/broken")
    outcome = provider.execute(_request(), "idem-2")
    assert outcome.status == EffectStatus.FAILED.value
    assert "500" in outcome.error


def test_a_timeout_is_unknown_because_the_server_may_have_acted(server):
    """The case the entire recovery protocol exists for."""
    provider = HttpEffectProvider(f"{server}/slow", timeout=0.3)
    outcome = provider.execute(_request(), "idem-3")
    assert outcome.status == EffectStatus.UNKNOWN.value
    assert "timeout" in outcome.error
    # The server did receive it: reporting FAILED here would have been a lie.
    assert any(entry["path"] == "/slow" for entry in RECEIVED)


def test_a_refused_connection_is_failed_because_nothing_happened():
    provider = HttpEffectProvider("http://127.0.0.1:1/never", timeout=1.0)
    outcome = provider.execute(_request(), "idem-4")
    assert outcome.status == EffectStatus.FAILED.value


def test_reconciliation_asks_and_does_not_act_again(server):
    provider = HttpEffectProvider(f"{server}/notify", reconcile_endpoint=f"{server}/status")
    provider.execute(_request(), "idem-5")
    posts_before = sum(1 for entry in RECEIVED if entry["method"] == "POST")

    settled = provider.reconcile(_request(), "idem-5")
    assert settled.status == EffectStatus.COMPLETED.value
    assert settled.result["body"]["settled"] is True
    assert sum(1 for entry in RECEIVED if entry["method"] == "POST") == posts_before


def test_without_a_reconcile_endpoint_the_effect_stays_a_human_decision(server):
    provider = HttpEffectProvider(f"{server}/notify")
    outcome = provider.reconcile(_request(), "idem-6")
    assert outcome.status == EffectStatus.UNKNOWN.value
    assert "human" in outcome.error


@pytest.mark.parametrize("endpoint", ["", "   ", "ftp://example.com", "example.com"])
def test_a_provider_must_be_configured_with_a_real_endpoint(endpoint):
    with pytest.raises(HttpProviderError):
        HttpEffectProvider(endpoint)


# --- the whole chain ---------------------------------------------------------

def _effect_decision(provider_capability: str, endpoint_payload: dict, *, decision_id: str, mission_id: str):
    contract = DelegationContract(mission_id, "Notify the operator", "notification delivered",
                                  autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("notify_operator", "Send one bounded notification", 4, 1, 9, contract_id=mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Operate reliably"), money=1, time=1, capability=2, energy=1,
                                freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions={name: 0.8 for name in profile.weights}, contract=contract,
        execution_target=provider_capability, execution_kind="external_effect",
        provider_name="http", provider_target="singular.providers.http_effect:HttpEffectProvider",
        operation="notify", execution_payload=endpoint_payload,
        decision_id=decision_id, capacity_budget=2,
    )


def _engine(tmp_path: Path, decision):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    coordinator = ExternalEffectCoordinator(runtime.store)
    engine = DurableExecutionEngine(runtime, effect_coordinator=coordinator)
    ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
    return engine


def test_a_validated_decision_produces_one_real_http_effect(server, tmp_path: Path):
    """Decision -> attestation -> capability -> lease -> real request -> record."""
    payload = {"message": "governed"}
    provider = HttpEffectProvider(f"{server}/notify", reconcile_endpoint=f"{server}/status")
    capability = register_execution_capability(provider)
    decision = _effect_decision(capability, payload, decision_id="DEC-HTTP-1", mission_id="MIS-HTTP-1")
    engine = _engine(tmp_path, decision)

    result = engine.execute_effect_validated(
        decision, provider, provider_name="http", operation="notify", payload=payload
    )

    assert result.status == "COMPLETED"
    posts = [entry for entry in RECEIVED if entry["method"] == "POST"]
    assert len(posts) == 1, "the world was touched exactly once"
    assert posts[0]["body"] == payload
    assert posts[0]["idempotency_key"], "the effect carried its idempotency key"


def test_replaying_the_same_decision_does_not_call_the_server_twice(server, tmp_path: Path):
    payload = {"message": "once"}
    provider = HttpEffectProvider(f"{server}/notify")
    capability = register_execution_capability(provider)
    decision = _effect_decision(capability, payload, decision_id="DEC-HTTP-2", mission_id="MIS-HTTP-2")
    engine = _engine(tmp_path, decision)

    first = engine.execute_effect_validated(decision, provider, provider_name="http", operation="notify", payload=payload)
    second = engine.execute_effect_validated(decision, provider, provider_name="http", operation="notify", payload=payload)

    assert first.status == "COMPLETED" and second.status == "COMPLETED"
    assert sum(1 for entry in RECEIVED if entry["method"] == "POST") == 1


def test_an_ambiguous_effect_is_quarantined_and_then_reconciled(server, tmp_path: Path):
    """The whole point: a timeout does not become a guess, and never a retry."""
    payload = {"message": "ambiguous"}
    provider = HttpEffectProvider(f"{server}/slow", timeout=0.3, reconcile_endpoint=f"{server}/status")
    capability = register_execution_capability(provider)
    decision = _effect_decision(capability, payload, decision_id="DEC-HTTP-3", mission_id="MIS-HTTP-3")
    engine = _engine(tmp_path, decision)

    ambiguous = engine.execute_effect_validated(
        decision, provider, provider_name="http", operation="notify", payload=payload
    )
    assert ambiguous.status == "RECOVERY_REQUIRED"
    posts_after_attempt = sum(1 for entry in RECEIVED if entry["method"] == "POST")

    settled = engine.reconcile_effect_validated(
        decision, provider, provider_name="http", operation="notify", payload=payload
    )
    assert settled.status == "COMPLETED"
    assert sum(1 for entry in RECEIVED if entry["method"] == "POST") == posts_after_attempt, (
        "reconciliation asked the server, it did not act again"
    )


def test_the_payload_the_decision_authorized_is_the_payload_that_is_sent(server, tmp_path: Path):
    payload = {"message": "authorized"}
    provider = HttpEffectProvider(f"{server}/notify")
    capability = register_execution_capability(provider)
    decision = _effect_decision(capability, payload, decision_id="DEC-HTTP-4", mission_id="MIS-HTTP-4")
    engine = _engine(tmp_path, decision)

    with pytest.raises(PermissionError, match="payload"):
        engine.execute_effect_validated(
            decision, provider, provider_name="http", operation="notify", payload={"message": "substituted"}
        )
    assert not [entry for entry in RECEIVED if entry["method"] == "POST"], "nothing reached the server"
