"""One governed external effect, end to end, in one file.

Run it:  python examples/governed_http_effect.py

It starts a local HTTP server, builds a decision through the full validation
pipeline, issues a durable attestation, and performs one real request through
the execution boundary -- then shows that replaying the decision does not touch
the server again, and that a substituted payload never reaches the network.

Nothing here is mocked. The socket is real, the SQLite database is real, and
every refusal below is the boundary refusing, not the example pretending.
"""
from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.effects import ExternalEffectCoordinator
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.providers import HttpEffectProvider
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision

CALLS: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"null")
        CALLS.append(body)
        raw = json.dumps({"delivered": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def build_decision(capability: str, payload: dict):
    """Every safety layer runs here; none of them can be skipped."""
    contract = DelegationContract("MIS-DEMO", "Notify the operator", "notification delivered",
                                  autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("notify_operator", "Send one bounded notification", 4, 1, 9, contract_id="MIS-DEMO")
    profile = TrajectoryProfile(Vision("Operate reliably"), money=1, time=1, capability=2, energy=1,
                                freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective,
        actions=(action,),
        action_to_intervention=((action.id, "career"),),
        domain_states=(DomainState(LearningDomain.CAREER, 0.2, confidence=0.9),),
        interventions=(Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1),),
        trajectory_profile=profile,
        trajectory_dimensions={name: 0.8 for name in profile.weights},
        contract=contract,
        execution_target=capability,
        execution_kind="external_effect",
        provider_name="http",
        provider_target="singular.providers.http_effect:HttpEffectProvider",
        operation="notify",
        execution_payload=payload,
        decision_id="DEC-DEMO",
        capacity_budget=2,
    )


def main() -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{httpd.server_address[1]}/notify"

    with tempfile.TemporaryDirectory() as directory:
        payload = {"message": "governed"}
        provider = HttpEffectProvider(endpoint)
        capability = register_execution_capability(provider)

        decision = build_decision(capability, payload)
        print(f"decision      {decision.decision_id}  fingerprint {decision.context_fingerprint[:16]}…")
        print(f"artifact      {decision.execution_artifact_fingerprint[:16]}…  (the code it authorizes)")

        store = DurableStore(Path(directory) / "singular.db")
        runtime = DurableMissionRuntime(store)
        runtime.store.save_mission(decision.contract)
        engine = DurableExecutionEngine(runtime, effect_coordinator=ExternalEffectCoordinator(store))
        ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
        print("attested      durably issued; a decision that is not attested cannot execute")

        result = engine.execute_effect_validated(
            decision, provider, provider_name="http", operation="notify", payload=payload
        )
        print(f"executed      {result.status}  server calls: {len(CALLS)}  body: {CALLS[-1]}")

        engine.execute_effect_validated(
            decision, provider, provider_name="http", operation="notify", payload=payload
        )
        print(f"replayed      same decision again  ->  server calls still {len(CALLS)}")

        try:
            engine.execute_effect_validated(
                decision, provider, provider_name="http", operation="notify", payload={"message": "substituted"}
            )
        except PermissionError as exc:
            print(f"refused       substituted payload  ->  {exc}")
        print(f"              server calls still {len(CALLS)}: nothing reached the network")

    httpd.shutdown()


if __name__ == "__main__":
    main()
