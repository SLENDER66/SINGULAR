"""Capability identity on the path whose effect leaves the process.

The handler path re-checked the capability immediately before calling the
handler, and required both the durable artifact record and the artifact the
decision names. The external-effect path -- the one with irreversible
consequences -- did neither at the same strength:

* execute_effect_validated checked the capability once, at the top, then went
  through governance and the durable claim before touching the provider, so a
  capability revoked in that window still produced a real external effect;
* reconcile_effect_validated relied on the in-process registry alone. That
  table is rebuilt from scratch after a restart, so a substituted provider
  registered under the old token could report an effect that never happened
  and have it confirmed as COMPLETED.
"""
import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.effects import ExternalEffectCoordinator, ProviderResult
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision

PAYLOAD = {"amount": 42, "target": "bounded"}


class BoundedProvider:
    """The authorized artifact. `mode` is instance state, not identity."""

    def __init__(self, mode: str = "COMPLETED") -> None:
        self.mode = mode
        self.calls: list[str] = []

    def execute(self, request, idempotency_key):
        self.calls.append("execute")
        return ProviderResult(self.mode, {"ok": True} if self.mode == "COMPLETED" else None, None)

    def reconcile(self, request, idempotency_key):
        self.calls.append("reconcile")
        return ProviderResult("COMPLETED", {"remote": True})


class SubstitutedProvider:
    """A different artifact wearing the same shape."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, request, idempotency_key):
        self.calls.append("execute")
        return ProviderResult("COMPLETED", {"forged": True})

    def reconcile(self, request, idempotency_key):
        self.calls.append("reconcile")
        return ProviderResult("COMPLETED", {"forged": True})


AUTHORIZED_PROVIDER = BoundedProvider()
AUTHORIZED_CAPABILITY = register_execution_capability(AUTHORIZED_PROVIDER, "cap_test_time_of_use_provider")


def _effect_decision(decision_id: str) -> object:
    contract = DelegationContract("MIS-TOU", "Improve career", "Career action completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2, energy=1,
                                freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract, execution_target=AUTHORIZED_CAPABILITY,
        execution_kind="external_effect", provider_name="bounded-provider",
        provider_target="tests.test_effect_capability_time_of_use:BoundedProvider",
        operation="apply", execution_payload=PAYLOAD, decision_id=decision_id, capacity_budget=2,
    )


def _executor(decision, tmp_path) -> DurableExecutionEngine:
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    executor = DurableExecutionEngine(runtime, effect_coordinator=ExternalEffectCoordinator(runtime.store))
    ValidatedDecisionIssuer(executor.attestation_store).issue(decision)
    return executor


def _external_effects(executor: DurableExecutionEngine) -> int:
    with executor.store._connect() as conn:
        return int(conn.execute("SELECT COUNT(*) AS total FROM external_effects").fetchone()["total"])


def _revoke_during(executor: DurableExecutionEngine, capability_id: str, method: str) -> None:
    """Revoke the capability inside the window the top-of-call checks left open."""
    original = getattr(executor, method)

    def revoking(*args, **kwargs):
        executor.capability_store.revoke(capability_id)
        return original(*args, **kwargs)

    setattr(executor, method, revoking)


def test_external_effect_refuses_a_capability_revoked_after_validation(tmp_path):
    decision = _effect_decision("DEC-TOU-REVOKE")
    executor = _executor(decision, tmp_path)
    _revoke_during(executor, decision.execution_target, "_authorize")

    with pytest.raises(PermissionError, match="n'est plus valide"):
        executor.execute_effect_validated(decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
                                          operation="apply", payload=PAYLOAD)

    assert AUTHORIZED_PROVIDER.calls == []
    assert _external_effects(executor) == 0


def test_reconciliation_refuses_an_artifact_the_decision_does_not_name(tmp_path, monkeypatch):
    """Models a restart: the in-process table is rebuilt, here from the wrong object."""
    import singular.execution as execution_module

    decision = _effect_decision("DEC-TOU-SUBST")
    executor = _executor(decision, tmp_path)
    monkeypatch.setattr(execution_module, "execution_capability_matches", lambda capability_id, target: True)
    substituted = SubstitutedProvider()

    with pytest.raises(PermissionError, match="L'artefact exécutable ne correspond pas"):
        executor.reconcile_effect_validated(decision, substituted, provider_name="bounded-provider",
                                            operation="apply", payload=PAYLOAD)

    assert substituted.calls == []


def test_a_refused_artifact_cannot_poison_the_token(tmp_path, monkeypatch):
    """The refusal must not bind the token to what it just refused."""
    import singular.execution as execution_module

    decision = _effect_decision("DEC-TOU-POISON")
    executor = _executor(decision, tmp_path)
    monkeypatch.setattr(execution_module, "execution_capability_matches", lambda capability_id, target: True)

    with pytest.raises(PermissionError):
        executor.reconcile_effect_validated(decision, SubstitutedProvider(), provider_name="bounded-provider",
                                            operation="apply", payload=PAYLOAD)

    assert executor.capability_store.get(decision.execution_target) is None
    executor.capability_store.bind(decision.execution_target, AUTHORIZED_PROVIDER)


def test_reconciliation_refuses_an_artifact_the_durable_record_denies(tmp_path, monkeypatch):
    import singular.execution as execution_module

    decision = _effect_decision("DEC-TOU-DURABLE")
    executor = _executor(decision, tmp_path)
    executor.capability_store.bind(decision.execution_target, AUTHORIZED_PROVIDER)
    monkeypatch.setattr(execution_module, "execution_capability_matches", lambda capability_id, target: True)
    monkeypatch.setattr(DurableExecutionEngine, "_require_decision_artifact", staticmethod(lambda decision, target: None))
    substituted = SubstitutedProvider()

    with pytest.raises(PermissionError, match="Capability durable identity refused"):
        executor.reconcile_effect_validated(decision, substituted, provider_name="bounded-provider",
                                            operation="apply", payload=PAYLOAD)

    assert substituted.calls == []


def test_authorized_external_effect_still_executes(tmp_path):
    """The added checks must not close the path they protect."""
    decision = _effect_decision("DEC-TOU-OK")
    executor = _executor(decision, tmp_path)
    provider = AUTHORIZED_PROVIDER
    provider.calls.clear()

    result = executor.execute_effect_validated(decision, provider, provider_name="bounded-provider",
                                               operation="apply", payload=PAYLOAD)

    assert result.status == "COMPLETED"
    assert provider.calls == ["execute"]
