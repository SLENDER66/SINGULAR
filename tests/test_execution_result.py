import pytest

from singular.autopilot import Autonomy, GovernorDecision
from singular.decision_engine import DecisionRecommendation, DecisionStatus
from singular.execution_result import (
    ExecutionIntent,
    ExecutionResult,
    ExecutionResultBridge,
    ExecutionStatus,
)


def recommendation(status: DecisionStatus = DecisionStatus.PROPOSED) -> DecisionRecommendation:
    return DecisionRecommendation(
        decision_id="d1",
        objective="build wealth",
        status=status,
        selected_option_id="a1",
        reports=(),
        rationale="test",
        confidence=0.9,
    )


def test_prepare_is_fail_closed_for_review() -> None:
    # Le motif est necessaire : le garde suivant -- `requires_human` -- attrape
    # aussi ce cas, puisque `requires_human` est vrai des que le statut n'est pas
    # PROPOSED. Sans le motif, ce test passait avec ce garde-ci retire, et prouvait
    # donc l'autre. Mesure, pas supposition.
    bridge = ExecutionResultBridge()
    with pytest.raises(PermissionError, match="Only a PROPOSED recommendation"):
        bridge.prepare(recommendation(DecisionStatus.REVIEW), idempotency_key="k1")


def test_prepare_then_authorize_reversible() -> None:
    bridge = ExecutionResultBridge()
    intent = bridge.prepare(recommendation(), idempotency_key="k1")
    authorized = bridge.authorize(
        intent,
        GovernorDecision("a1", Autonomy.EXECUTE_REVERSIBLE, ("low risk",)),
    )
    assert authorized.authorization_id is None
    assert authorized.action_id == "a1"


def test_authorized_execution_requires_approval_reference() -> None:
    bridge = ExecutionResultBridge()
    intent = bridge.prepare(recommendation(), idempotency_key="k1")
    with pytest.raises(PermissionError):
        bridge.authorize(
            intent,
            GovernorDecision("a1", Autonomy.EXECUTE_AUTHORIZED, ("approved class",)),
        )


def test_terminal_result_validates_success_flag() -> None:
    with pytest.raises(ValueError):
        from singular.execution_result import ExecutionResult

        ExecutionResult("d1", "a1", "k1", ExecutionStatus.SUCCEEDED, False)


def test_idempotency_returns_first_result_and_rejects_replay_mismatch() -> None:
    bridge = ExecutionResultBridge()
    intent = ExecutionIntent("d1", "a1", "k1")
    first = bridge.record(
        intent,
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        observed_value=42.0,
        metadata={"source": "system", "attempt": 1},
    )
    same = bridge.record(
        intent,
        status=ExecutionStatus.SUCCEEDED,
        success=True,
        observed_value=42.0,
        metadata={"attempt": 1, "source": "system"},
    )
    assert same is first
    with pytest.raises(RuntimeError):
        bridge.record(
            intent,
            status=ExecutionStatus.SUCCEEDED,
            success=True,
            observed_value=99.0,
            metadata={"attempt": 1, "source": "system"},
        )


def test_results_are_sorted_by_idempotency_key() -> None:
    bridge = ExecutionResultBridge()
    bridge.record(ExecutionIntent("d", "a", "z"), status=ExecutionStatus.FAILED, success=False, error="x")
    bridge.record(ExecutionIntent("d", "b", "a"), status=ExecutionStatus.SUCCEEDED, success=True, observed_value=True)
    assert [item.idempotency_key for item in bridge.results()] == ["a", "z"]


# --- les refus de la passerelle que rien n'essayait ------------------------------
#
# `ExecutionResultBridge` tient la separation que la section 6 du mandat nomme :
# intelligence != decision != autorisation != execution. Une recommandation est une
# proposition, jamais une permission ; une decision du gouverneur autorise **une**
# action, pas l'action qu'on lui presente ensuite.
#
# La passe de mutation a nomme six de ses refus sans temoin. Tous sont atteignables
# par l'API publique, et le premier d'entre eux l'est meme par le moteur de
# decision.


def _rapport_avec_avertissement(action_id: str = "a2"):
    """Un rapport qui demande un humain sans dire REVIEW : un simple avertissement.

    `GlobalDecisionReport.requires_human` est vrai des qu'il y a un avertissement.
    C'est ce qui rend le garde suivant atteignable **par le moteur** et non
    seulement a la main : le moteur ne regarde `requires_human` que sur l'option
    retenue, et ne passe en REVIEW que si une option *dit* REVIEW. Une option non
    retenue qui porte un avertissement laisse donc le statut a PROPOSED pendant que
    la recommandation, elle, demande un humain.
    """
    from singular.global_control import GlobalDecisionReport

    return GlobalDecisionReport(
        objective="build wealth", action_id=action_id, decision="PROCEED",
        blockers=(), warnings=("CAPACITY:REDUCE_SCOPE",), capacity_recommendation=None,
        policy_tier="GREEN", policy_requires_human=False,
        governor_mode=Autonomy.EXECUTE_REVERSIBLE, red_team_findings=(), coherence=None,
    )


def test_prepare_refuse_une_recommandation_qui_demande_un_humain() -> None:
    rapport = _rapport_avec_avertissement()
    assert rapport.requires_human is True

    proposition = DecisionRecommendation(
        decision_id="d1", objective="build wealth", status=DecisionStatus.PROPOSED,
        selected_option_id="a1", reports=(rapport,), rationale="test", confidence=0.9,
    )
    assert proposition.requires_human is True

    with pytest.raises(PermissionError, match="Human review is required"):
        ExecutionResultBridge().prepare(proposition, idempotency_key="k1")


def test_prepare_refuse_une_recommandation_sans_option_retenue() -> None:
    """Preparer « rien » donnerait une intention dont l'action est `None`."""
    sans_option = DecisionRecommendation(
        decision_id="d1", objective="build wealth", status=DecisionStatus.PROPOSED,
        selected_option_id=None, reports=(), rationale="test", confidence=0.9,
    )
    with pytest.raises(ValueError, match="without a selected option"):
        ExecutionResultBridge().prepare(sans_option, idempotency_key="k1")


@pytest.mark.parametrize("cle", ["", "   ", "\t"])
def test_prepare_exige_une_cle_d_idempotence(cle) -> None:
    """La cle est ce qui empeche la double execution : vide, elle n'empeche rien.

    Deux intentions de cle vide partageraient la meme entree du registre, donc la
    seconde recevrait le resultat de la premiere -- ou serait refusee comme une
    reutilisation, selon ce qu'elle porte. Les deux sont faux.
    """
    with pytest.raises(ValueError, match="idempotency_key is required"):
        ExecutionResultBridge().prepare(recommendation(), idempotency_key=cle)


def test_authorize_refuse_une_autorisation_donnee_pour_une_autre_action() -> None:
    """Le depute confus, dans sa forme la plus directe.

    Le gouverneur autorise une action nommee. Presenter cette autorisation avec une
    autre intention, c'est faire executer B avec la permission de A -- et rien
    d'autre ne le verrait : l'intention est bien formee, la decision du gouverneur
    est authentique, seul le rapprochement des deux est faux.
    """
    bridge = ExecutionResultBridge()
    intention = bridge.prepare(recommendation(), idempotency_key="k1")

    with pytest.raises(PermissionError, match="does not match the requested action"):
        bridge.authorize(intention, GovernorDecision("une-autre", Autonomy.EXECUTE_REVERSIBLE, ("ok",)))


@pytest.mark.parametrize("mode", [Autonomy.BLOCK, Autonomy.PREPARE, Autonomy.ESCALATE])
def test_authorize_refuse_un_mode_qui_n_autorise_pas_l_execution(mode) -> None:
    """PREPARE prepare, ESCALATE attend un humain, BLOCK refuse : aucun n'execute.

    ESCALATE est le cas qui compte : il porte un identifiant d'approbation, donc il
    *ressemble* a une autorisation. Il dit exactement l'inverse -- qu'un humain n'a
    pas encore tranche.
    """
    bridge = ExecutionResultBridge()
    intention = bridge.prepare(recommendation(), idempotency_key="k1")

    with pytest.raises(PermissionError, match="Governor did not authorize execution"):
        bridge.authorize(intention, GovernorDecision("a1", mode, ("raison",), "APR-12345678"))


# --- l'observation elle-meme : un resultat qui se contredit n'est pas une mesure --
#
# `ExecutionResult` est ce que le grand livre des resultats, l'apprentissage
# economique et la calibration lisent ensuite. Un enregistrement qui dit SUCCEEDED
# avec `success=False`, ou FAILED sans erreur, n'est pas une mesure imprecise :
# c'est deux affirmations contradictoires dans la meme ligne, et le lecteur suivant
# en croira une au hasard.


def _resultat(**remplacements):
    valeurs = {"decision_id": "d1", "action_id": "a1", "idempotency_key": "k1",
               "status": ExecutionStatus.SUCCEEDED, "success": True}
    valeurs.update(remplacements)
    return ExecutionResult(**valeurs)


def test_le_trajet_nominal_du_resultat_se_construit() -> None:
    """Sans ca, les refus suivants passeraient en ne gardant rien."""
    assert _resultat().status is ExecutionStatus.SUCCEEDED


@pytest.mark.parametrize("champ", ["decision_id", "action_id"])
@pytest.mark.parametrize("vide", ["", "   "])
def test_un_resultat_nomme_la_decision_et_l_action(champ, vide) -> None:
    """Les deux moities du meme garde, jouees separement.

    Un resultat sans decision ne peut pas etre rapproche de ce qui l'a autorise ;
    un resultat sans action ne peut pas etre rapproche de ce qui a ete fait. Les
    deux sont la trace, pas des etiquettes.
    """
    with pytest.raises(ValueError, match="decision_id and action_id are required"):
        _resultat(**{champ: vide})


@pytest.mark.parametrize("vide", ["", "   "])
def test_un_resultat_porte_sa_cle_d_idempotence(vide) -> None:
    with pytest.raises(ValueError, match="idempotency_key is required"):
        _resultat(idempotency_key=vide)


def test_un_succes_qui_dit_ne_pas_avoir_reussi_est_refuse() -> None:
    with pytest.raises(ValueError, match="SUCCEEDED requires success=True"):
        _resultat(status=ExecutionStatus.SUCCEEDED, success=False)


@pytest.mark.parametrize("statut", [ExecutionStatus.FAILED, ExecutionStatus.REJECTED])
def test_un_echec_qui_dit_avoir_reussi_est_refuse(statut) -> None:
    with pytest.raises(ValueError, match="FAILED/REJECTED require success=False"):
        _resultat(status=statut, success=True, error="quelque chose")


def test_un_echec_sans_erreur_est_refuse() -> None:
    """Un echec dont personne ne dit la cause ne se corrige pas et ne s'apprend pas."""
    with pytest.raises(ValueError, match="FAILED requires an error"):
        _resultat(status=ExecutionStatus.FAILED, success=False)


def test_les_metadonnees_sont_ordonnees_ou_refusees() -> None:
    """L'ordre n'est pas une politesse : l'empreinte d'un resultat en depend.

    `ExecutionResultBridge.record` refuse une cle d'idempotence reutilisee pour un
    resultat different, en comparant des empreintes. Deux enregistrements portant
    les memes couples dans deux ordres auraient deux empreintes : la meme execution
    passerait pour deux, ou pour une contradiction.
    """
    with pytest.raises(ValueError, match="metadata must be deterministically sorted"):
        _resultat(metadata=(("b", "2"), ("a", "1")))

    assert _resultat(metadata=(("a", "1"), ("b", "2"))).metadata == (("a", "1"), ("b", "2"))


def test_authorize_accepte_une_execution_autorisee_qui_porte_sa_reference() -> None:
    """Le cas positif du garde d'approbation, qui manquait.

    Le refus voisin -- EXECUTE_AUTHORIZED sans reference -- avait son temoin ; celui
    qui dit que la reference **suffit** n'existait pas. Un garde dont seul le refus
    est prouve peut devenir un refus permanent sans que rien ne rougisse, et une
    autorisation humaine qui ne passe jamais est une porte murée.

    La reference d'approbation traverse jusqu'a l'intention : c'est elle qui relie
    l'execution au verdict humain qui l'a permise.
    """
    bridge = ExecutionResultBridge()
    intention = bridge.prepare(recommendation(), idempotency_key="k1")

    autorisee = bridge.authorize(
        intention,
        GovernorDecision("a1", Autonomy.EXECUTE_AUTHORIZED, ("classe approuvée",), "APR-12345678"),
    )
    assert autorisee.authorization_id == "APR-12345678"
    assert autorisee.action_id == "a1"
    assert autorisee.idempotency_key == "k1"
