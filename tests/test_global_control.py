import sqlite3

from singular.autopilot import ActionRequest, Autonomy
from singular.coherence import GlobalCoherenceGuard
from singular.consistency import CrossDomainConsistencyChecker
from singular.global_control import GlobalDecisionGate
from singular.human_optimization import DomainState, HumanOptimizationEngine, Intervention
from singular.models import Risk
from singular.state import CapacitySnapshot
from singular.trajectory import TrajectoryProfile
from singular.values import CoreValue, ValueAssessment, ValuesEngine, Vision
from singular.world_model import EpistemicType, WorldFact, WorldModel
from singular.domain_learning import LearningDomain


def action(**overrides):
    data = {"name": "draft_plan", "description": "Préparer un plan", "impact": 8, "risk": 2, "reversibility": 8}
    data.update(overrides)
    return ActionRequest(**data)


def test_global_gate_proceeds_when_domains_are_coherent():
    world = WorldModel()
    world.upsert("objectives", WorldFact("o1", "stabiliser", EpistemicType.OBJECTIVE))
    values = [ValuesEngine.assess(CoreValue("freedom"), ValueAssessment.ALIGNED, "compatible")]
    report = GlobalDecisionGate().evaluate("stabiliser", action(), world_model=world, values=values, capacity=CapacitySnapshot(1, 0.1, 0.0, 1.0), effort=0.2)
    assert report.decision == "PROCEED"
    assert report.blockers == ()


def test_global_gate_propagates_global_trajectory_review():
    profile = TrajectoryProfile(Vision("Build durable freedom and ownership."))
    report = GlobalDecisionGate().evaluate("grow", action(), trajectory_profile=profile, trajectory_dimensions={"money": 0.9})
    assert report.decision == "REVIEW"
    assert report.trajectory is not None
    assert report.trajectory.human_review is True
    assert "TRAJECTORY:REVIEW" in report.warnings


def test_global_gate_blocks_value_violation():
    values = [ValuesEngine.assess(CoreValue("respect"), ValueAssessment.VIOLATED, "conflict")]
    report = GlobalDecisionGate().evaluate("objectif", action(), values=values)
    assert report.decision == "BLOCK"
    # The blocker names the violated value verbatim; upper-casing it would lose
    # which value it was when two differ only by case.
    assert "VALUES:HARD_CONSTRAINT_VIOLATED:respect" in report.blockers


def test_global_gate_reviews_unknown_values_and_low_confidence_state():
    values = [ValuesEngine.assess(CoreValue("freedom"), ValueAssessment.UNKNOWN)]
    report = GlobalDecisionGate().evaluate("objectif", action(), values=values, capacity=CapacitySnapshot(0.8, 0.2, 0.0, 0.4), effort=0.1)
    assert report.decision == "REVIEW"
    assert "VALUES:UNKNOWN_REQUIRES_HUMAN_REVIEW" in report.warnings
    assert "CAPACITY:CLARIFY_STATE" in report.warnings


def test_global_gate_blocks_high_risk_irreversible_risk():
    risk = Risk(id="r1", name="critical", probability=1.0, impact=9, reversibility=1)
    report = GlobalDecisionGate().evaluate("objectif", action(), risks=[risk])
    assert report.decision == "BLOCK"
    assert "RISK:HIGH_EXPOSURE:r1" in report.blockers


def test_global_gate_never_executes_sensitive_action():
    report = GlobalDecisionGate().evaluate("objectif", action(name="wire_money", sensitive=True))
    assert report.decision == "BLOCK"
    assert report.policy_tier == "BLACK"
    assert report.governor_mode.value == "ESCALATE"


def test_global_gate_carries_human_optimization_into_trajectory_control():
    human_report = HumanOptimizationEngine.optimize(
        (DomainState(LearningDomain.CAREER, 0.2, confidence=0.4, leverage=1.0),),
        (Intervention("career", LearningDomain.CAREER, 0.8, evidence=0.9, causal_confidence=0.9),),
    )
    report = GlobalDecisionGate().evaluate("career", action(), human_optimization=human_report)
    assert report.human_optimization is human_report
    assert report.decision == "REVIEW"
    assert "HUMAN_OPTIMIZATION:LOW_STATE_CONFIDENCE" in report.warnings


def test_global_gate_fails_closed_on_durable_coherence_violation(tmp_path):
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE mission_states (mission_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE executions (execution_key TEXT PRIMARY KEY, mission_id TEXT NOT NULL, action_id TEXT, status TEXT NOT NULL)")
        conn.execute("CREATE TABLE external_effects (provider_idempotency_key TEXT PRIMARY KEY, execution_key TEXT NOT NULL, status TEXT NOT NULL)")
        conn.execute("INSERT INTO mission_states VALUES ('M1', 'COMPLETED')")
        conn.execute("INSERT INTO executions VALUES ('E1', 'M1', 'A1', 'RUNNING')")
        conn.commit()

    gate = GlobalDecisionGate(coherence_guard=GlobalCoherenceGuard(CrossDomainConsistencyChecker(db)))
    report = gate.evaluate("objectif", action(), mission_id="M1")
    assert report.decision == "BLOCK"
    assert "COHERENCE:MISSION_COMPLETED_WITH_NONTERMINAL_EXECUTION" in report.blockers


# --- les deux proprietes que tout le reste lit ----------------------------------
#
# `can_prepare` et `requires_human` sont les deux verdicts du rapport global. La
# frontiere les croit : `ValidatedTrajectoryDecision._validate` refuse un rapport
# qui exige un humain, et la politique doit permettre la preparation.
#
# Ce module ne leve aucun refus -- il rend des verdicts -- donc l'outil de mutation
# n'y voyait rien avant sa quatrieme forme. Elle neutralise une raison a la fois, et
# nomme celles que personne n'essaie.


def _portefeuille_vide():
    from singular.trajectory_optimization import TrajectoryPortfolio

    return TrajectoryPortfolio((), 0.0, 0.0, 0.0, 0.0)


def _profil_et_dimensions():
    profil = TrajectoryProfile(Vision("Build durable freedom and ownership."),
                               money=1, time=1, capability=2, energy=1, freedom=1,
                               ownership=1, learning=2, resilience=1, transmission=1)
    return profil, {nom: 0.8 for nom in profil.weights}


def test_un_blocage_suffit_a_interdire_la_preparation():
    """La moitie `not self.blockers` de `can_prepare`, que rien n'essayait.

    L'autre moitie -- `policy_tier != "BLACK"` -- ne peut jamais decider seule : un
    rang BLACK vient toujours avec `can_prepare=False` dans la politique, et la
    porte ajoute alors un blocage POLICY. C'est une assurance, pas un trou ; celle
    qui porte vraiment est celle-ci.

    Le cas joue est un portefeuille de trajectoire vide : la porte bloque, le rang
    reste GREEN. Sans ce garde, une action bloquee resterait preparable.
    """
    profil, dimensions = _profil_et_dimensions()
    rapport = GlobalDecisionGate().evaluate(
        "grow", action(), trajectory_profile=profil, trajectory_dimensions=dimensions,
        trajectory_portfolio=_portefeuille_vide(),
    )

    assert rapport.blockers, "le cas doit produire un blocage"
    assert rapport.policy_tier != "BLACK", "et un rang qui n'est pas BLACK, sinon l'autre moitie suffirait"
    assert rapport.can_prepare is False


def test_la_politique_seule_suffit_a_exiger_un_humain():
    """La moitie `policy_requires_human` de `requires_human`, que rien n'isolait.

    Cinq raisons d'exiger un humain, reliees par des `or` : un avertissement, la
    politique, un gouverneur qui escalade, une deliberation non resolue, une
    trajectoire a revoir. Une raison qui n'est prouvee par aucun test peut
    disparaitre sans que rien ne rougisse -- et c'est toute une categorie d'actions
    qui cesserait d'exiger un humain.

    Le piege est que les raisons se declenchent souvent ensemble : une action
    sensible fait passer la politique a BLACK **et** escalader le gouverneur, donc un
    test la-dessus ne prouve ni l'une ni l'autre. Il faut une action qui n'active
    qu'une raison.

    Celle-ci : un risque de 5 met la politique en ORANGE -- qui exige un humain --
    pendant que le gouverneur n'escalade qu'a partir de 8. Aucun avertissement, pas
    de trajectoire, pas de deliberation.
    """
    rapport = GlobalDecisionGate().evaluate("grow", action(risk=5))

    assert rapport.policy_requires_human is True
    assert rapport.warnings == (), "un avertissement suffirait deja, la raison ne serait plus isolee"
    assert rapport.governor_mode is not Autonomy.ESCALATE
    assert rapport.requires_human is True


# La quatrieme raison -- une deliberation non resolue -- ne peut jamais decider
# seule, et c'est mesure : quand `deliberation.unresolved` est vrai, la porte a
# deja ajoute l'avertissement `COLLECTIVE:UNRESOLVED_DELIBERATION`, donc la
# premiere raison a repondu avant. Assurance derriere un autre mecanisme, pas
# moitie morte : retirer cet avertissement la rendrait portante du jour au
# lendemain.
#
# Les trois autres raisons -- avertissement, gouverneur qui escalade, trajectoire a
# revoir -- sont deja prouvees par les tests de ce fichier. Celle des avertissements
# l'est par `test_global_gate_reviews_unknown_values_and_low_confidence_state` ;
# verifie en la neutralisant.
