"""Le moteur ne croit pas son coordinateur sur parole : il relit la preuve.

`_reconcile_effect_authorized` demande au coordinateur de réconcilier un effet
externe resté ambigu. Si la réponse est COMPLETED, il **relit** la ligne durable
avant de confirmer l'exécution, et refuse si elle ne dit pas la même chose.

Ce refus n'avait aucun témoin : neutralisé, la suite entière restait verte. Ce
qu'il empêche est le pire résultat que cette frontière puisse produire — une
exécution marquée COMPLETED, une mission finalisée, sur la seule parole d'un
collaborateur, sans qu'aucune preuve durable ne dise que l'effet a eu lieu.

Un coordinateur est injecté dans le constructeur : le substituer est une couture
prévue, pas un contournement de la frontière. La décision, l'attestation, la
capacité et le fournisseur restent les vrais.
"""
from __future__ import annotations

import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.decision_attestation import ValidatedDecisionIssuer
from singular.domain_learning import LearningDomain
from singular.durable import DurableStore
from singular.effects import EffectStatus, ExternalEffectCoordinator, ProviderResult
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision

CAPABILITY = "create_calendar_event"
PAYLOAD = {"slot": "2026-09-21T10:00", "duration": 30}


class AmbiguousProvider:
    """Le fournisseur autorisé. Il laisse l'effet ambigu, puis dit l'avoir fait."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, request, idempotency_key):
        self.calls.append("execute")
        return ProviderResult("UNKNOWN", None, None)

    def reconcile(self, request, idempotency_key):
        self.calls.append("reconcile")
        return ProviderResult("COMPLETED", {"booked": True})


PROVIDER = AmbiguousProvider()
PROVIDER_CAPABILITY = register_execution_capability(PROVIDER, "cap_preuve_durable_provider")
PROVIDER_TARGET = "tests.test_preuve_durable_de_l_effet:AmbiguousProvider"


class CoordinateurQuiAffirmeSansEcrire(ExternalEffectCoordinator):
    """Il annonce COMPLETED et laisse la ligne durable telle qu'elle est.

    C'est la forme la plus simple d'une écriture perdue : le coordinateur a
    répondu, la transaction n'a pas tenu. Vu du moteur, c'est indiscernable d'un
    collaborateur qui ment -- et c'est pour ça que le moteur relit.
    """

    def reconcile(self, request, provider) -> ProviderResult:
        self._authorize_reconciliation(request)
        return ProviderResult(EffectStatus.COMPLETED.value, {"booked": True}, None)


def _decision(decision_id: str):
    contract = DelegationContract("MIS-PREUVE", "Tenir l'agenda", "Créneau posé",
                                  autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest(CAPABILITY, "poser un créneau", 4, 3, 9,
                           contract_id="MIS-PREUVE", capability=CAPABILITY,
                           execution_capability=PROVIDER_CAPABILITY)
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


def _engine(decision, tmp_path, coordinateur=ExternalEffectCoordinator):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    engine = DurableExecutionEngine(runtime, effect_coordinator=coordinateur(runtime.store))
    ValidatedDecisionIssuer(engine.attestation_store).issue(decision)
    return engine


def _cle(engine, decision) -> str:
    return engine.store.idempotency_key("execute", decision.contract.mission_id,
                                        decision.global_report.action_id)


def _en_quarantaine(engine, decision):
    """L'effet part, revient ambigu, et l'exécution attend sa réconciliation."""
    PROVIDER.calls.clear()
    resultat = engine.execute_effect_validated(decision, PROVIDER, provider_name="booking",
                                               operation="book", payload=PAYLOAD)
    assert resultat.status == "RECOVERY_REQUIRED", "l'effet doit être en quarantaine"
    return resultat


def test_une_reconciliation_sans_preuve_durable_est_refusee(tmp_path):
    """COMPLETED annoncé, ligne durable inchangée : l'exécution ne se confirme pas."""
    decision = _decision("DEC-PREUVE-MENTEUR")
    engine = _engine(decision, tmp_path, CoordinateurQuiAffirmeSansEcrire)
    _en_quarantaine(engine, decision)

    with pytest.raises(RuntimeError, match="preuve durable"):
        engine.reconcile_effect_validated(decision, PROVIDER, provider_name="booking",
                                          operation="book", payload=PAYLOAD)

    ligne = engine.store.get_execution(_cle(engine, decision))
    assert ligne["status"] == "RECOVERY_REQUIRED", (
        "sans preuve, l'exécution reste ambiguë plutôt que de devenir COMPLETED")


def test_le_meme_chemin_confirme_quand_la_preuve_existe(tmp_path):
    """Sans ça, le test ci-dessus passerait pour la mauvaise raison.

    Il doit échouer parce que la preuve manque, pas parce que ce chemin refuse
    tout. Le vrai coordinateur écrit la ligne, et la même réconciliation aboutit.
    """
    decision = _decision("DEC-PREUVE-HONNETE")
    engine = _engine(decision, tmp_path)
    _en_quarantaine(engine, decision)

    resultat = engine.reconcile_effect_validated(decision, PROVIDER, provider_name="booking",
                                                 operation="book", payload=PAYLOAD)

    assert resultat.status == "COMPLETED"
    assert "reconcile" in PROVIDER.calls
