"""Ce qu'un durcissement de politique fait à un effet externe resté ambigu.

Point de départ : `reconcile_effect_validated` n'appelle pas
`_assert_policy_unchanged`, contrairement aux deux chemins d'exécution. Ça
ressemblait à un trou — un durcissement de politique qui refuserait une nouvelle
exécution mais laisserait passer une réconciliation, laquelle peut finaliser une
mission en COMPLETED.

Ce n'en est pas un, et ces tests le prouvent plutôt que de le raisonner :
`ValidatedTrajectoryDecision._validate` recalcule `ActionPolicy.evaluate` et
`verify()` échoue dès que la politique a bougé. Les trois chemins commencent par
`verify()`, donc les trois refusent. `_assert_policy_unchanged` est une défense
en profondeur, pas la seule garde.

Mais la vraie conséquence est l'inverse de celle que je cherchais, et elle est
plus gênante : **un durcissement de politique rend un effet externe ambigu
définitivement irréconciliable.** L'effet a expiré, on ne sait pas s'il a eu
lieu, et la seule opération supportée pour le découvrir — demander au
fournisseur — devient impossible. Refuser de demander ne défait pas un virement
qui serait parti.

C'est la même forme que le scan d'intégrité global corrigé plus tôt : une garde
de sécurité qui se transforme en impasse permanente, sans opération de sortie.
La différence est qu'ici la sortie demanderait de séparer « cette décision
est-elle encore exécutable » de « cette décision est-elle authentique et
désigne-t-elle bien cet effet », ce qui touche à la frontière elle-même. Ces
tests figent l'état réel pour que la décision se prenne sur preuve.
"""
from __future__ import annotations

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract, Governor
from singular.capabilities import CapabilityRegistry, CapabilitySpec
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.effects import ExternalEffectCoordinator, ProviderResult
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.security import ActionPolicy
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision

#: Une capacité nommée sans validation humaine, pour que la décision soit
#: exécutable, et resserrable pour provoquer la dérive.
CAPABILITY = "create_calendar_event"
PAYLOAD = {"slot": "2026-09-20T10:00", "duration": 30}


class BookingProvider:
    """Le fournisseur autorisé. `mode` est un état d'instance, pas une identité."""

    def __init__(self, mode: str = "UNKNOWN") -> None:
        self.mode = mode
        self.calls: list[str] = []

    def execute(self, request, idempotency_key):
        self.calls.append("execute")
        return ProviderResult(self.mode, None, None)

    def reconcile(self, request, idempotency_key):
        self.calls.append("reconcile")
        return ProviderResult("COMPLETED", {"booked": True})


PROVIDER = BookingProvider()
PROVIDER_CAPABILITY = register_execution_capability(PROVIDER, "cap_policy_drift_provider")
PROVIDER_TARGET = "tests.test_reconciliation_policy_drift:BookingProvider"


@pytest.fixture
def tighten():
    """Resserrer la capacité nommée, et la remettre — elle est globale."""
    original = CapabilityRegistry._SPECS[CAPABILITY]

    def apply() -> None:
        CapabilityRegistry._SPECS[CAPABILITY] = CapabilitySpec(
            CAPABILITY, 1, original.min_reversibility, False, original.allowed_action_names
        )

    yield apply
    CapabilityRegistry._SPECS[CAPABILITY] = original


def _action() -> ActionRequest:
    return ActionRequest(CAPABILITY, "poser un créneau", 4, 3, 9,
                         contract_id="MIS-DRIFT", capability=CAPABILITY,
                         execution_capability=PROVIDER_CAPABILITY)


def _decision(decision_id: str = "DEC-DRIFT"):
    contract = DelegationContract("MIS-DRIFT", "Tenir l'agenda", "Créneau posé",
                                  autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = _action()
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9,
                                causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Tenir un agenda qui tient"), money=1, time=1, capability=2,
                                energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,),
        action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions={name: 0.8 for name in profile.weights}, contract=contract,
        execution_target=PROVIDER_CAPABILITY, decision_id=decision_id, capacity_budget=2,
        execution_kind="external_effect", provider_name="booking",
        provider_target=PROVIDER_TARGET, operation="book", execution_payload=PAYLOAD,
    )


def _engine(decision, tmp_path) -> DurableExecutionEngine:
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    engine = DurableExecutionEngine(runtime, effect_coordinator=ExternalEffectCoordinator(runtime.store))
    ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
    return engine


def _call(engine, decision, method: str):
    return getattr(engine, method)(decision, PROVIDER, provider_name="booking",
                                   operation="book", payload=PAYLOAD)


# --- pourquoi ça ressemblait à un trou ---------------------------------------

def test_the_governor_does_not_notice_a_policy_that_tightened(tighten):
    """La raison du soupçon, figée : l'égalité des gouverneurs ne couvre pas ça.

    `Governor.evaluate` ne lit ni `ActionPolicy` ni le registre des capacités
    nommées. Si un jour quelqu'un retire la revérification de politique en se
    disant que la comparaison des gouverneurs suffit, ce test le contredit.
    """
    contract = DelegationContract("MIS-DRIFT", "o", "r", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = _action()

    before_policy = ActionPolicy.evaluate(action)
    before_governor = Governor.evaluate(action, contract)
    tighten()
    after_policy = ActionPolicy.evaluate(action)
    after_governor = Governor.evaluate(action, contract)

    assert before_policy != after_policy, "le durcissement doit changer la politique"
    assert before_governor == after_governor, "et laisser le gouverneur identique"


# --- pourquoi ce n'en est pas un ---------------------------------------------

def test_verify_recomputes_the_policy_and_refuses_when_it_moved(tighten):
    """La garde réelle, et elle est en amont des trois chemins."""
    decision = _decision("DEC-DRIFT-VERIFY")
    assert decision.verify() is True
    tighten()
    assert decision.verify() is False


def test_all_three_paths_refuse_a_decision_whose_policy_moved(tmp_path, tighten):
    decision = _decision("DEC-DRIFT-ALL")
    engine = _engine(decision, tmp_path)
    tighten()

    with pytest.raises(PermissionError, match="missing or invalid"):
        engine.execute_validated(decision, lambda action: None)
    for method in ("execute_effect_validated", "reconcile_effect_validated"):
        with pytest.raises(PermissionError, match="missing or invalid"):
            _call(engine, decision, method)


# --- la conséquence, qui est le vrai sujet -----------------------------------

def test_a_tightened_policy_strands_an_ambiguous_external_effect(tmp_path, tighten):
    """L'impasse, prouvée de bout en bout plutôt que raisonnée.

    L'effet a expiré : personne ne sait s'il a eu lieu. La seule opération
    supportée pour le découvrir est de demander au fournisseur. Un durcissement
    de politique la rend impossible — et refuser de demander ne défait pas ce
    qui serait parti.
    """
    decision = _decision("DEC-DRIFT-STRANDED")
    engine = _engine(decision, tmp_path)
    PROVIDER.mode = "UNKNOWN"
    PROVIDER.calls.clear()

    result = _call(engine, decision, "execute_effect_validated")
    assert result.status == "RECOVERY_REQUIRED", "l'effet doit être en quarantaine"
    assert "execute" in PROVIDER.calls

    tighten()
    with pytest.raises(PermissionError):
        _call(engine, decision, "reconcile_effect_validated")

    assert "reconcile" not in PROVIDER.calls, "le fournisseur n'a jamais été interrogé"
    row = engine.store.get_execution(
        engine.store.idempotency_key("execute", decision.contract.mission_id,
                                     decision.global_report.action_id))
    assert row["status"] == "RECOVERY_REQUIRED", "et l'exécution reste ambiguë, sans sortie"


def test_without_the_tightening_the_same_effect_is_reconcilable(tmp_path):
    """La preuve que l'impasse vient bien de la politique, et de rien d'autre."""
    decision = _decision("DEC-DRIFT-OK")
    engine = _engine(decision, tmp_path)
    PROVIDER.mode = "UNKNOWN"
    PROVIDER.calls.clear()

    assert _call(engine, decision, "execute_effect_validated").status == "RECOVERY_REQUIRED"
    assert _call(engine, decision, "reconcile_effect_validated").status == "COMPLETED"
    assert "reconcile" in PROVIDER.calls
