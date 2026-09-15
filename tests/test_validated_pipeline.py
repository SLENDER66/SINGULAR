import pytest

from singular.autopilot import ActionRequest, Autonomy, DelegationContract
from singular.decision_attestation import DecisionAttestationStore, ValidatedDecisionIssuer
from singular.durable import DurableStore
from singular.execution import DurableExecutionEngine
from singular.execution_capability import register_execution_capability
from singular.human_optimization import DomainState, Intervention
from singular.domain_learning import LearningDomain
from singular.mission_runtime import DurableMissionRuntime
from singular.trajectory import TrajectoryProfile
from singular.validated_pipeline import ValidatedTrajectoryPipeline
from singular.values import Vision
from singular.validated_trajectory_decision import payload_fingerprint


def authorized_handler(action):
    return {"action_id": action.id, "executed": True}


AUTHORIZED_HANDLER_CAPABILITY = register_execution_capability(authorized_handler, "cap_test_authorized_handler")


def _inputs():
    contract = DelegationContract("MIS-PIPE", "Improve career", "Career action completed", autonomy=Autonomy.EXECUTE_REVERSIBLE)
    action = ActionRequest("career_test", "Run bounded career test", 4, 1, 9, contract_id=contract.mission_id)
    state = DomainState(LearningDomain.CAREER, 0.2, confidence=0.9)
    intervention = Intervention("career", LearningDomain.CAREER, 0.9, evidence=0.9, causal_confidence=0.9, capacity=1)
    profile = TrajectoryProfile(Vision("Build a resilient long-term career"), money=1, time=1, capability=2, energy=1, freedom=1, ownership=1, learning=2, resilience=1, transmission=1)
    dimensions = {name: 0.8 for name in profile.weights}
    return contract, action, state, intervention, profile, dimensions


def _build_decision():
    """Le trajet nominal. Les arguments vivent dans `_build_avec`, plus bas.

    Ils etaient ecrits deux fois depuis que les temoins de la porte d'entree
    existent -- et deux copies d'un jeu d'arguments finissent par ne plus decrire le
    meme trajet, ce qui ferait mentir les deux moities du fichier l'une sur l'autre.
    """
    return _build_avec()


def _attested_executor(decision, tmp_path):
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    executor = DurableExecutionEngine(runtime)
    ValidatedDecisionIssuer(executor.attestation_store).issue(decision)
    return executor


def test_pipeline_constructs_decision_only_after_all_required_stages():
    decision = _build_decision()
    assert decision.verify() is True
    assert decision.global_report.decision == "PROCEED"
    assert decision.trajectory_portfolio.candidates[0].intervention_id == "career"


def test_pipeline_can_issue_durable_attestation_as_final_build_stage(tmp_path):
    contract, action, state, intervention, profile, dimensions = _inputs()
    store = DecisionAttestationStore(tmp_path / "attestations.db")
    decision, attestation = ValidatedTrajectoryPipeline.build_and_attest(
        attestation_store=store, issuer="pipeline-test",
        objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target=AUTHORIZED_HANDLER_CAPABILITY, decision_id="DEC-PIPE-ATTEST", capacity_budget=2,
    )
    assert attestation.decision_id == decision.decision_id
    assert store.verify(decision)


def test_pipeline_fails_closed_when_trajectory_requires_review():
    """An incomplete trajectory picture must never be silently optimized over.

    This used to lower one dimension to -0.2. TrajectoryEngine clamps dimensions
    to [-1, 1] and weights money 1 of 11, so that input scores 0.71 and proceeds:
    the test only passed because the pipeline was refusing every build for an
    unrelated reason. Drop the dimension instead, which is what actually raises
    MISSING_DIMENSION and puts the assessment in REVIEW.
    """
    contract, action, state, intervention, profile, dimensions = _inputs()
    del dimensions["money"]
    with pytest.raises(PermissionError, match="Global decision gate refused|Trajectory requires"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target=AUTHORIZED_HANDLER_CAPABILITY,
            decision_id="DEC-PIPE-BLOCK", capacity_budget=2,
        )


def test_pipeline_rejects_action_outside_selected_portfolio():
    contract, action, state, intervention, profile, dimensions = _inputs()
    with pytest.raises(PermissionError, match="outside the selected trajectory portfolio"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(action,), action_to_intervention=((action.id, "wrong-intervention"),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target=AUTHORIZED_HANDLER_CAPABILITY,
            decision_id="DEC-PIPE-MISMATCH", capacity_budget=2,
        )


def test_pipeline_rejects_symbolic_execution_target_without_capability():
    contract, action, state, intervention, profile, dimensions = _inputs()
    with pytest.raises(ValueError, match="opaque execution capability"):
        ValidatedTrajectoryPipeline.build(
            objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
            domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
            trajectory_dimensions=dimensions, contract=contract,
            execution_target="tests.test_validated_pipeline:authorized_handler",
            decision_id="DEC-PIPE-SYMBOLIC", capacity_budget=2,
        )


def test_decision_temporal_window_is_enforced():
    decision = _build_decision()
    assert decision.verify(now=decision.issued_at) is True
    assert decision.verify(now=decision.expires_at) is False
    assert decision.verify(now=decision.issued_at - 0.001) is False


def test_decision_expiry_is_fingerprinted():
    decision = _build_decision()
    original_expiry = decision.expires_at
    object.__setattr__(decision, "expires_at", original_expiry + 1)
    assert decision.verify() is False


def test_executor_rejects_handler_substitution_before_handler_call(tmp_path):
    decision = _build_decision()
    executor = _attested_executor(decision, tmp_path)
    calls = []

    def wrong_handler(action):
        calls.append("wrong")

    with pytest.raises(PermissionError, match="Handler capability"):
        executor.execute_validated(decision, wrong_handler)

    assert calls == []


def test_executor_rejects_unattested_valid_decision(tmp_path):
    decision = _build_decision()
    runtime = DurableMissionRuntime(DurableStore(tmp_path / "singular.db"))
    runtime.store.save_mission(decision.contract)
    executor = DurableExecutionEngine(runtime)
    with pytest.raises(PermissionError, match="durablement attestée"):
        executor.execute_validated(decision, authorized_handler)


def test_executor_accepts_only_the_bound_handler(tmp_path):
    decision = _build_decision()
    executor = _attested_executor(decision, tmp_path)

    result = executor.execute_validated(decision, authorized_handler)

    assert result.status == "COMPLETED"
    assert result.result["executed"] is True


def test_executor_rejects_forged_callable_metadata(tmp_path):
    decision = _build_decision()
    executor = _attested_executor(decision, tmp_path)

    def forged_handler(action):
        return {"action_id": action.id, "executed": False}

    forged_handler.__module__ = authorized_handler.__module__
    forged_handler.__qualname__ = authorized_handler.__qualname__
    with pytest.raises(PermissionError, match="Handler capability"):
        executor.execute_validated(decision, forged_handler)


class AuthorizedProvider:
    def execute(self, request, idempotency_key):
        raise AssertionError("provider should not be called by substitution tests")

    def reconcile(self, request, idempotency_key):
        raise AssertionError("provider should not be called by substitution tests")


class OtherProvider(AuthorizedProvider):
    pass


AUTHORIZED_PROVIDER = AuthorizedProvider()
AUTHORIZED_PROVIDER_CAPABILITY = register_execution_capability(AUTHORIZED_PROVIDER, "cap_test_authorized_provider")


def _build_effect_decision():
    contract, action, state, intervention, profile, dimensions = _inputs()
    payload = {"amount": 42, "target": "bounded"}
    return ValidatedTrajectoryPipeline.build(
        objective=contract.objective, actions=(action,), action_to_intervention=((action.id, intervention.id),),
        domain_states=(state,), interventions=(intervention,), trajectory_profile=profile,
        trajectory_dimensions=dimensions, contract=contract,
        execution_target=AUTHORIZED_PROVIDER_CAPABILITY, execution_kind="external_effect",
        provider_name="bounded-provider", provider_target="tests.test_validated_pipeline:AuthorizedProvider",
        operation="apply", execution_payload=payload, decision_id="DEC-EFFECT", capacity_budget=2,
    ), payload


def test_executor_rejects_provider_substitution_before_runtime_access(tmp_path):
    decision, _ = _build_effect_decision()
    executor = _attested_executor(decision, tmp_path)
    with pytest.raises(PermissionError, match="Provider capability"):
        executor.execute_effect_validated(decision, OtherProvider(), provider_name="bounded-provider", operation="apply", payload={"amount": 42, "target": "bounded"})


def test_executor_rejects_operation_substitution_before_runtime_access(tmp_path):
    decision, payload = _build_effect_decision()
    executor = _attested_executor(decision, tmp_path)
    with pytest.raises(PermissionError, match="Provider or operation"):
        executor.execute_effect_validated(decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider", operation="delete", payload=payload)


def test_executor_rejects_payload_substitution_before_runtime_access(tmp_path):
    decision, _ = _build_effect_decision()
    executor = _attested_executor(decision, tmp_path)
    with pytest.raises(PermissionError, match="payload"):
        executor.execute_effect_validated(decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider", operation="apply", payload={"amount": 43, "target": "bounded"})


def test_payload_fingerprint_is_stable_for_equivalent_mapping_order():
    assert payload_fingerprint({"b": 2, "a": 1}) == payload_fingerprint({"a": 1, "b": 2})


# --- la porte d'entree du seul producteur de decisions validees -----------------
#
# La passe de mutation sur `validated_pipeline.py` nomme d'abord ses cinq premiers
# refus, tous non prouves : aucun test n'appelait `build` avec un argument
# malforme. C'est la porte d'entree du seul objet que la frontiere accepte, et elle
# n'etait verifiee qu'en marchant droit.
#
# Les cinq sont atteignables par l'API publique -- `decision_id` vaut meme `""` par
# defaut, donc oublier de le passer suffit. Ce ne sont pas des assurances : sans
# eux, un appelant construit une decision dont l'objectif est vide, dont
# l'identifiant n'existe pas, ou qui autorise plusieurs actions la ou tout le reste
# du systeme en suppose une seule.


def _build_avec(**remplacements):
    """Le trajet nominal, avec un argument remplace. Rien d'autre ne change."""
    contract, action, state, intervention, profile, dimensions = _inputs()
    arguments = {
        "objective": contract.objective, "actions": (action,),
        "action_to_intervention": ((action.id, intervention.id),),
        "domain_states": (state,), "interventions": (intervention,),
        "trajectory_profile": profile, "trajectory_dimensions": dimensions,
        "contract": contract, "execution_target": AUTHORIZED_HANDLER_CAPABILITY,
        "decision_id": "DEC-PIPE", "capacity_budget": 2,
    }
    arguments.update(remplacements)
    return ValidatedTrajectoryPipeline.build(**arguments)


def test_le_trajet_nominal_de_ce_fichier_construit_bien(tmp_path):
    """Sans ca, les six tests suivants passeraient en ne prouvant rien."""
    assert _build_avec().verify() is True


@pytest.mark.parametrize("objectif", ["", "   "])
def test_le_pipeline_refuse_un_objectif_vide(objectif):
    with pytest.raises(ValueError, match="objective cannot be empty"):
        _build_avec(objective=objectif)


def test_le_pipeline_refuse_zero_ou_plusieurs_actions():
    """« Exactement une » n'est pas une preference : tout le reste en depend.

    `_validate` designe l'action autorisee par `global_report.action_id`, la
    politique et le gouverneur sont calcules sur `actions[0]`, et la capacite
    d'execution est posee sur cette action-la. Deux actions, et les cinq autres
    etages parleraient de la premiere en ayant l'air d'en autoriser deux.
    """
    contract, action, state, intervention, profile, dimensions = _inputs()
    seconde = ActionRequest("autre", "Une seconde action", 4, 1, 9, contract_id=contract.mission_id)

    with pytest.raises(ValueError, match="exactly one action"):
        _build_avec(actions=())
    with pytest.raises(ValueError, match="exactly one action"):
        _build_avec(actions=(action, seconde),
                    action_to_intervention=((action.id, intervention.id), (seconde.id, intervention.id)))


@pytest.mark.parametrize("identifiant", ["", "   "])
def test_le_pipeline_refuse_une_decision_sans_identifiant(identifiant):
    """Et c'est la valeur par defaut : `decision_id: str = ""`.

    L'identifiant est ce qui lie la decision a son attestation durable et a sa cle
    d'execution. Une decision anonyme se ferait passer pour une autre.
    """
    with pytest.raises(ValueError, match="decision_id is required"):
        _build_avec(decision_id=identifiant)


def test_le_pipeline_refuse_un_objectif_qui_n_est_pas_celui_du_contrat():
    """Le contrat est l'autorisation ; l'objectif dit pour quoi elle vaut.

    Les deux doivent nommer la meme chose, sinon la decision serait autorisee par un
    contrat qui parle d'autre chose. `_validate` le reverifie plus tard contre le
    rapport global ; ici c'est refuse a la porte, avec le bon message.
    """
    with pytest.raises(ValueError, match="must match the execution contract"):
        _build_avec(objective="Un autre objectif")


@pytest.mark.parametrize("genre", ["", "effect", "handler ", "EXTERNAL_EFFECT", "autre"])
def test_le_pipeline_refuse_un_genre_d_execution_inconnu(genre):
    """Deux genres, et rien d'autre : la frontiere ne sait executer que ces deux-la.

    Un troisieme mot passerait ici, puis les deux branches du bas -- liaison de
    fournisseur exigee ou interdite -- le traiteraient comme s'il etait « handler »,
    ce qui est exactement la mauvaise reponse par defaut.
    """
    with pytest.raises(ValueError, match="execution_kind must be handler or external_effect"):
        _build_avec(execution_kind=genre)


# --- la fenetre de validite, et les nombres qui n'en sont pas -------------------
#
# La suite des memes refus non prouves : tout ce qui borde la duree de vie d'une
# decision. La section 7 du mandat nomme NaN et l'infini parmi les choses a chercher
# activement, et ce sont justement les valeurs que ces gardes attrapent -- une
# decision dont la fin de validite vaut `inf` n'expire jamais.
#
# `_validate` reverifie la fenetre a la construction de l'objet, mais sans `now` :
# il refuse un intervalle incoherent, pas un intervalle **passe** ou **futur**. Les
# deux refus qui comparent a l'horloge n'existent qu'ici.


@pytest.mark.parametrize("duree", [0, -1, -0.001, float("nan"), float("inf"), float("-inf")])
def test_le_pipeline_refuse_une_duree_de_vie_qui_n_en_est_pas_une(duree):
    with pytest.raises(ValueError, match="decision_ttl_seconds must be finite and positive"):
        _build_avec(decision_ttl_seconds=duree)


def test_le_pipeline_refuse_une_fenetre_de_validite_incoherente():
    """Fin avant debut, fin egale au debut, et les deux bornes non finies.

    Une fenetre vide autoriserait une decision que rien ne peut executer ; une borne
    infinie autoriserait une decision qui n'expire jamais, ce qui est la meme chose
    qu'une autorisation permanente.
    """
    from time import time

    maintenant = time()
    for debut, fin in ((maintenant, maintenant - 1), (maintenant, maintenant),
                       (float("nan"), maintenant + 300), (maintenant, float("nan")),
                       (float("-inf"), maintenant + 300), (maintenant, float("inf"))):
        with pytest.raises(ValueError, match="decision validity interval is invalid"):
            _build_avec(issued_at=debut, expires_at=fin)


def test_le_pipeline_refuse_une_decision_emise_dans_le_futur():
    """Antidater vers l'avant, c'est se donner une autorisation qui n'a pas commence.

    Le cas n'est pas theorique : une horloge qui avance, ou un appelant qui calcule
    sa fenetre a partir d'une date de planification. Ce refus compare a l'horloge,
    donc `_validate` -- qui verifie la coherence de l'intervalle sans regarder
    l'heure -- ne le rattrape pas.
    """
    from time import time

    demain = time() + 86400
    with pytest.raises(ValueError, match="issued_at cannot be in the future"):
        _build_avec(issued_at=demain, expires_at=demain + 300)


def test_le_pipeline_refuse_une_decision_deja_expiree():
    """L'autre bord de la meme fenetre : une decision morte avant d'etre construite.

    `ValidatedTrajectoryDecision.__post_init__` refuserait aussi, puisqu'il valide
    avec l'heure courante -- mais deux etages plus loin et avec un autre message. Ce
    refus-ci est celui qui dit a l'appelant que sa fenetre est le probleme.
    """
    from time import time

    hier = time() - 86400
    with pytest.raises(ValueError, match="expires_at must be in the future"):
        _build_avec(issued_at=hier, expires_at=hier + 300)


@pytest.mark.parametrize("budget", [None, -1, float("nan"), float("inf"), float("-inf")])
def test_le_pipeline_refuse_un_budget_de_capacite_qui_n_en_est_pas_un(budget):
    """`capacity_budget` vaut `None` par defaut : l'oublier tombe ici.

    Il borne l'optimisation humaine et le portefeuille, et `_validate` les
    reconstruit avec cette meme valeur. Un budget infini ferait entrer toutes les
    interventions dans le portefeuille ; un budget NaN rendrait chaque comparaison
    fausse sans rien lever.
    """
    with pytest.raises(ValueError, match="capacity_budget is required"):
        _build_avec(capacity_budget=budget)


@pytest.mark.parametrize("maximum", [0, -1])
def test_le_pipeline_refuse_un_portefeuille_sans_place(maximum):
    with pytest.raises(ValueError, match="max_portfolio_candidates must be positive"):
        _build_avec(max_portfolio_candidates=maximum)


def test_le_pipeline_refuse_deux_interventions_de_meme_identifiant():
    """Deux interventions de meme identifiant se fondent en une, silencieusement.

    `{item.id: item for item in interventions}` garde la derniere. Le portefeuille
    serait alors optimise sur moins d'interventions que la decision n'en
    enregistre, et `_validate` -- qui reconstruit la table de la meme facon --
    referait le meme repli sans rien voir.

    Qui refuse : `HumanOptimizationEngine.optimize`, appele juste apres la table.
    Le pipeline portait une copie du meme controle, avec le meme message ; retiree,
    aucun test ne rougissait. Ce test-ci prouve donc que **la porte refuse**, et le
    moteur est le seul domicile de la regle.
    """
    from singular.domain_learning import LearningDomain
    from singular.human_optimization import Intervention

    _, _, _, intervention, _, _ = _inputs()
    jumelle = Intervention("career", LearningDomain.CAREER, 0.5, evidence=0.5,
                           causal_confidence=0.5, capacity=1)
    assert jumelle.id == intervention.id, "le doublon doit porter le meme identifiant"

    # Le motif est ancre : `_validate` refuse le meme doublon avec « **validated**
    # intervention ids must be unique », dont celui-ci est un sous-texte. Sans les
    # ancres, ce test passait avec le garde du pipeline retire -- mesure, pas
    # supposition -- et prouvait donc l'autre garde, pas celui-ci.
    with pytest.raises(ValueError, match=r"^intervention ids must be unique$"):
        _build_avec(interventions=(intervention, jumelle))


@pytest.mark.parametrize("budget", [0, 0.5])
def test_le_pipeline_refuse_un_portefeuille_vide(budget):
    """Rien a faire n'est pas une autorisation de ne rien faire.

    L'intervention de ce trajet coute une unite de capacite. Sous ce cout, elle est
    ecartee, le portefeuille sort vide, et il n'y a plus d'action selectionnee a
    autoriser. Sans ce refus, la construction continuerait avec un portefeuille
    sans candidat : la decision nommerait une action que l'optimisation n'a pas
    retenue, et la liaison action -> intervention qui la justifie ne designerait
    rien.

    Le cas est atteignable sans rien truquer -- un budget de capacite plus petit que
    ce que l'action demande -- et c'est le genre de journee ordinaire, pas une
    attaque.
    """
    with pytest.raises(PermissionError, match="No executable trajectory portfolio"):
        _build_avec(capacity_budget=budget)


def test_le_pipeline_refuse_une_liaison_qui_ne_designe_pas_l_action():
    """La liaison action -> intervention doit parler de l'action autorisee.

    C'est elle qui justifie l'action par une intervention du portefeuille : le
    refus suivant verifie que l'intervention nommee a bien ete retenue. Si la
    liaison designe une autre action, la decision porte une justification qui ne
    concerne pas ce qu'elle autorise -- et le controle suivant, lui, la lirait
    quand meme et la trouverait valide.
    """
    _, action, _, intervention, _, _ = _inputs()

    with pytest.raises(ValueError, match="exactly one intervention mapping"):
        _build_avec(action_to_intervention=(("une-autre-action", intervention.id),))
    with pytest.raises(ValueError, match="exactly one intervention mapping"):
        _build_avec(action_to_intervention=())
    with pytest.raises(ValueError, match="exactly one intervention mapping"):
        _build_avec(action_to_intervention=((action.id, intervention.id),
                                            (action.id, "career")))


@pytest.mark.parametrize("fourni", ["issued_at", "expires_at"])
def test_le_pipeline_refuse_une_seule_borne_de_fenetre(fourni):
    """Les deux bornes se donnent ensemble, ou pas du tout.

    Une seule fournie, et l'autre serait calculee depuis l'horloge : la decision
    porterait une fenetre dont une moitie vient de l'appelant et l'autre du hasard
    du moment. Le refus est a la porte parce qu'apres, il n'y a plus moyen de
    savoir laquelle des deux etait voulue.
    """
    from time import time

    maintenant = time()
    valeurs = {"issued_at": maintenant - 10, "expires_at": maintenant + 300}
    with pytest.raises(ValueError, match="must be supplied together"):
        _build_avec(**{fourni: valeurs[fourni]})


def test_une_execution_par_gestionnaire_ne_porte_aucune_liaison_de_fournisseur():
    """Les deux genres d'execution ne se melangent pas, meme a moitie.

    Un « handler » s'execute dans ce processus ; un « external_effect » part chez un
    fournisseur, sous une cle d'idempotence et une empreinte de charge. Une decision
    qui serait l'un en portant les champs de l'autre laisserait le lecteur -- code ou
    humain -- choisir lequel croire.
    """
    for champ, valeur in (("provider_name", "banque"), ("provider_target", "compte-1"),
                          ("operation", "virement"), ("execution_payload", {"montant": 42})):
        with pytest.raises(ValueError, match="handler execution cannot carry external-effect binding"):
            _build_avec(**{champ: valeur})


@pytest.mark.parametrize("manquant", ["provider_name", "provider_target", "operation"])
def test_un_effet_externe_exige_sa_liaison_complete(manquant):
    """Trois champs, et aucun ne se devine.

    Le fournisseur, sa cible et l'operation forment ensemble l'identite de l'effet
    qui partira dans le monde ; la decision les scelle dans son empreinte. Il en
    manque un, et l'effet reconcilie plus tard ne pourrait pas etre reconnu comme
    celui qui avait ete autorise.
    """
    liaison = {"provider_name": "banque", "provider_target": "compte-1", "operation": "virement",
               "execution_payload": {"montant": 42}}
    liaison[manquant] = None
    with pytest.raises(ValueError, match="external-effect execution requires provider binding"):
        _build_avec(execution_kind="external_effect", **liaison)


def test_une_seconde_correspondance_pour_la_meme_action_est_refusee():
    """`dict()` fait disparaitre un doublon sans le dire, et c'est une substitution.

    `action_to_intervention` arrive comme une suite de paires, et la porte en fait
    un dictionnaire. Deux paires pour la **meme** action s'effondrent en une : la
    seconde ecrase la premiere, en silence, et c'est elle qui decidera de quelle
    intervention la decision se reclame.

    Le garde compare donc les deux longueurs avant de regarder quoi que ce soit
    d'autre. Sa voisine -- « la clef doit etre l'action autorisee » -- ne voit
    rien ici : les deux paires nomment la bonne action. Seule la longueur separe
    le cas legitime du doublon, et rien ne l'essayait.
    """
    contract, action, state, intervention, profile, dimensions = _inputs()

    # L'action doit etre **celle** que la porte recoit : `_build_avec` appelle
    # `_inputs()` pour son compte, et un identifiant d'action est tire au hasard a
    # chaque fois. Une premiere ecriture de ce test ne passait pas la meme action,
    # donc c'est la moitie voisine -- « la clef doit etre l'action autorisee » --
    # qui refusait, et le doublon n'etait jamais atteint. Le controle par
    # l'inverse l'a dit ; la phrase seule ne l'aurait pas dit.
    with pytest.raises(ValueError, match="exactly one intervention mapping"):
        _build_avec(actions=(action,), interventions=(intervention,),
                    domain_states=(state,), contract=contract,
                    objective=contract.objective,
                    trajectory_profile=profile, trajectory_dimensions=dimensions,
                    action_to_intervention=((action.id, intervention.id),
                                            (action.id, intervention.id)))
