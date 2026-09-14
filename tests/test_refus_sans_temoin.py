"""Les refus de la frontiere que personne n'essayait.

« Les tests passent » ne dit pas quels refus sont prouves.
`tools/gardes_sans_test.py` le mesure : il neutralise chaque `if ... raise` des
modules de la frontiere, un par un, et relance la suite. Premiere passe :
**60 refus sur 146 survivaient** -- retirables sans qu'un seul test rougisse.

Ils ne sont pas 60 trous. Trois familles, et il faut les distinguer avant
d'ecrire une ligne :

1. *Atteignable, et personne ne l'essaie.* C'est ce fichier.
2. *Couvert par un controle anterieur.* La plupart des refus de
   `validated_execution.py` : une decision qui les violerait aurait une autre
   empreinte, donc `verify()` la refuse avant. Assurances, pas trous -- leur
   ecrire un test demanderait de desactiver `verify()`, donc de tester un chemin
   qui n'existe pas.
3. *Rien ne produit leur entree.* Les quatre refus lies a l'approbation humaine :
   une decision validee ne peut pas porter ESCALATE. C'est ce que le README
   annonce -- « human approval is currently not an authorization channel » -- et
   la passe de mutation le mesure au lieu de le croire.

Ce que la premiere famille avait de plus net : **la reconciliation**. La
substitution de fournisseur, d'operation et de charge est testee sur le chemin
d'execution (`test_validated_pipeline.py`) et pas sur celui de la reconciliation,
qui atteint le meme fournisseur et peut faire passer une execution a COMPLETED.

Et, en dessous, deux refus du coordinateur et du registre de capacites qui
gardent chacun un cas qu'on ne veut pas voir arriver : un effet ambigu rejoue, et
une capacite durable relue sous un autre interpreteur.
"""
from __future__ import annotations

import pytest

from singular.autopilot import Autonomy
from singular.durable import DurableStore, MissionStatus
from singular.effects import ExternalEffectCoordinator
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.security import ActionPolicy
from tests.support import build_decision
from tests.test_validated_pipeline import (
    AUTHORIZED_PROVIDER,
    OtherProvider,
    _build_decision,
    _build_effect_decision,
    authorized_handler,
)


def _moteur(decision, tmp_path, *, avec_coordinateur: bool = True):
    """Un moteur reel sur une base reelle, attestation comprise. Pas de faux executeur."""
    from singular.decision_attestation import ValidatedDecisionIssuer

    store = DurableStore(tmp_path / "singular.db")
    runtime = DurableMissionRuntime(store)
    runtime.store.save_mission(decision.contract)
    coordinateur = ExternalEffectCoordinator(store) if avec_coordinateur else None
    moteur = DurableExecutionEngine(runtime, effect_coordinator=coordinateur)
    ValidatedDecisionIssuer(moteur.attestation_store).issue(decision)
    return moteur


def _pendant(moteur, methode: str, geste) -> None:
    """Fait `geste` dans la fenetre que les controles du haut de l'appel laissent ouverte.

    Meme forme que `_revoke_during` de `test_effect_capability_time_of_use.py` :
    une revocation qui arrive avant l'appel serait refusee par le premier garde,
    donc elle ne prouverait rien du dernier.
    """
    original = getattr(moteur, methode)

    def enveloppe(*args, **kwargs):
        geste()
        return original(*args, **kwargs)

    setattr(moteur, methode, enveloppe)



# --- le genre d'execution, dans les deux sens ---------------------------------

def test_une_decision_d_effet_ne_passe_pas_par_le_chemin_du_handler(tmp_path):
    decision, _ = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="bound to an external effect"):
        moteur.execute_validated(decision, authorized_handler)


def test_une_decision_de_handler_ne_passe_pas_par_le_chemin_de_l_effet(tmp_path):
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="not bound to an external effect"):
        moteur.execute_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload={"amount": 42, "target": "bounded"},
        )


def test_une_decision_de_handler_ne_passe_pas_par_la_reconciliation(tmp_path):
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="not bound to an external effect"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload={"amount": 42, "target": "bounded"},
        )


# --- la reconciliation refuse les memes substitutions que l'execution ---------
#
# Elle atteint le meme fournisseur et peut confirmer une execution COMPLETED :
# ce qui est refuse a l'aller doit l'etre au retour, et rien ne le verifiait.

def test_la_reconciliation_refuse_un_fournisseur_substitue(tmp_path):
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="Provider capability"):
        moteur.reconcile_effect_validated(
            decision, OtherProvider(), provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


def test_la_reconciliation_refuse_une_operation_substituee(tmp_path):
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="Provider or operation"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="delete", payload=payload,
        )


def test_la_reconciliation_refuse_un_fournisseur_renomme(tmp_path):
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="Provider or operation"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="autre-provider",
            operation="apply", payload=payload,
        )


def test_la_reconciliation_refuse_une_charge_substituee(tmp_path):
    """Le cas qui compte : la charge decide de ce que le fournisseur ira confirmer."""
    decision, _ = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="payload does not match"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload={"amount": 43, "target": "bounded"},
        )


def test_la_reconciliation_exige_un_coordinateur(tmp_path):
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path, avec_coordinateur=False)

    with pytest.raises(RuntimeError, match="ExternalEffectCoordinator"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


def test_l_execution_d_un_effet_exige_un_coordinateur(tmp_path):
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path, avec_coordinateur=False)

    with pytest.raises(RuntimeError, match="ExternalEffectCoordinator"):
        moteur.execute_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


def test_la_reconciliation_exige_une_execution_en_recuperation(tmp_path):
    """Rien a reconcilier tant qu'aucune ambiguite n'a ete persistee."""
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(ValueError, match="RECOVERY_REQUIRED"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


# --- la derive entre l'emission et l'execution --------------------------------
#
# Une decision est attestee, puis l'etat durable change. Le moteur ne relit pas
# le verdict porte par la decision : il le recalcule sur le contrat que la base
# contient maintenant, et refuse s'ils diffèrent. C'est le seul scenario qui
# atteint ces refus, et il n'etait joue nulle part.
#
# `save_mission` refuse une mission modifiee -- « L'identite d'une mission
# existante est immuable » -- donc l'alteration se fait en SQL, ce qui est
# exactement le cas a couvrir : quelqu'un a touche a l'enregistrement durable.


def _altere_le_contrat_durable(store: DurableStore, mission_id: str, **champs) -> None:
    import json

    with store._connect() as conn:
        charge = json.loads(conn.execute(
            "SELECT payload FROM missions WHERE mission_id=?", (mission_id,)).fetchone()["payload"])
        charge.update(champs)
        conn.execute("UPDATE missions SET payload=? WHERE mission_id=?",
                     (json.dumps(charge, sort_keys=True), mission_id))


def test_un_contrat_durable_altere_apres_l_emission_refuse_l_execution(tmp_path):
    """L'autonomie du contrat a change : le gouverneur d'aujourd'hui n'est plus celui-la."""
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)
    _altere_le_contrat_durable(moteur.store, decision.contract.mission_id,
                               autonomy=Autonomy.EXECUTE_AUTHORIZED.value)

    with pytest.raises(PermissionError, match="governance no longer matches"):
        moteur.execute_validated(decision, authorized_handler)


def test_un_contrat_durable_altere_apres_l_emission_refuse_aussi_l_effet(tmp_path):
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)
    _altere_le_contrat_durable(moteur.store, decision.contract.mission_id,
                               autonomy=Autonomy.EXECUTE_AUTHORIZED.value)

    with pytest.raises(PermissionError, match="governance no longer matches"):
        moteur.execute_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


def test_un_contrat_qui_interdit_l_action_depuis_l_emission_bloque(tmp_path):
    """L'interdiction arrivee apres coup gagne contre un PROCEED deja atteste."""
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)
    nom = decision.authorized_actions[0].name
    _altere_le_contrat_durable(moteur.store, decision.contract.mission_id,
                               forbidden_actions=[nom])

    with pytest.raises(PermissionError, match="bloquée par la gouvernance"):
        moteur.execute_validated(decision, authorized_handler)


def test_une_politique_reconstruite_differente_refuse_l_execution(tmp_path, monkeypatch):
    """La politique est reconstruite, jamais relue sur la decision.

    Ce refus a deja ete faux dans les deux sens : il lisait `governed.policy`, un
    attribut que `GovernedAction` n'a pas, a travers un `getattr` avec None par
    defaut -- donc il refusait tout, et le meme `getattr` rendant la valeur de la
    decision aurait tout accepte. Il n'avait aucun test ; il en a deux.

    Le remplacant ne vise que le nom que le moteur emploie pour reconstruire
    (`singular.execution.ActionPolicy`) : `ActionPolicy` est aussi celle que la
    gouvernance evalue, et la durcir partout ferait rougir un refus different,
    une ligne plus haut.
    """
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)

    class PolitiqueQuiADerive:
        @staticmethod
        def evaluate(action):
            from dataclasses import replace as _replace
            return _replace(ActionPolicy.evaluate(action), requires_human=True)

    monkeypatch.setattr("singular.execution.ActionPolicy", PolitiqueQuiADerive)

    with pytest.raises(PermissionError, match="policy no longer matches"):
        moteur.execute_validated(decision, authorized_handler)


def test_un_rang_de_politique_qui_derive_refuse_aussi(tmp_path, monkeypatch):
    """Le rang est compare a part : la politique peut coincider et le rang, non."""
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)
    vraie = ActionPolicy.evaluate

    class RangQuiADerive:
        @staticmethod
        def evaluate(action):
            return vraie(action)

    # Le moteur compare `governed.policy_tier` au rang de la decision. On garde
    # la politique identique et on fait deriver le rang que la gouvernance a
    # calcule, ce qui est le cas ou les deux controles ne disent pas la meme
    # chose -- celui pour lequel le second existe.
    from dataclasses import replace as _replace
    gouverne = moteur.runtime.route

    def route_avec_un_autre_rang(action, mission_id=None):
        return _replace(gouverne(action, mission_id), policy_tier="BLACK")

    monkeypatch.setattr(moteur.runtime, "route", route_avec_un_autre_rang)
    monkeypatch.setattr("singular.execution.ActionPolicy", RangQuiADerive)

    with pytest.raises(PermissionError, match="governance tier no longer matches"):
        moteur.execute_validated(decision, authorized_handler)


def test_une_mission_deja_terminee_ne_recoit_plus_d_execution(tmp_path):
    """L'etat de la mission derive aussi, et pas seulement son contrat.

    Une mission COMPLETED qui n'a pas d'execution sous cette cle : la decision est
    valide, attestee, et le moteur refuse quand meme. C'est le refus qui empeche
    de rouvrir une mission close par une decision emise avant sa fermeture.
    """
    from singular.durable import MissionStatus

    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)
    with moteur.store._connect() as conn:
        conn.execute("UPDATE mission_states SET status=? WHERE mission_id=?",
                     (MissionStatus.COMPLETED.value, decision.contract.mission_id))

    with pytest.raises(ValueError, match="doit être PLANNED"):
        moteur.execute_validated(decision, authorized_handler)


# --- le bail ------------------------------------------------------------------

@pytest.mark.parametrize("bail", [0, -1])
def test_un_bail_non_positif_est_refuse_a_la_construction(tmp_path, bail):
    """Un bail nul rend toute execution immediatement perimee.

    La suivante lirait une execution eventee, donc une recuperation a demander a
    un fournisseur -- une ambiguite inventee sur un effet qui n'a jamais commence.
    """
    decision = _build_decision()
    store = DurableStore(tmp_path / "singular.db")
    runtime = DurableMissionRuntime(store)
    runtime.store.save_mission(decision.contract)

    with pytest.raises(ValueError):
        DurableExecutionEngine(runtime, execution_lease_seconds=bail)


# --- et l'adaptateur, aux deux endroits ou il etait seul ----------------------

def test_l_adaptateur_refuse_aussi_une_decision_de_handler_sur_le_chemin_de_l_effet(tmp_path):
    """Le meme refus existe aux deux etages, et ni l'un ni l'autre n'avait de test."""
    from singular.validated_execution import ValidatedExecutionBoundary

    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)
    frontiere = ValidatedExecutionBoundary(moteur)

    with pytest.raises(PermissionError, match="n'autorise pas un effet externe"):
        frontiere.execute_effect(
            decision, decision.global_report.action_id, AUTHORIZED_PROVIDER,
            provider_name="bounded-provider", operation="apply", payload={"amount": 42},
        )


@pytest.mark.parametrize("chemin", ["execute_effect", "reconcile_effect"])
def test_l_adaptateur_refuse_un_fournisseur_renomme(tmp_path, chemin):
    """Le meme trou que dans le moteur, dans la copie que porte l'adaptateur.

    `_validate_effect_binding` sert les deux chemins d'effet de l'adaptateur et
    compare deux choses dans la meme ligne : le nom du fournisseur et l'operation.
    Seule l'operation etait essayee -- ici comme dans le moteur. Le nom decide de
    quel cote du reseau part l'effet, et il est ce qu'un appelant fournit.
    """
    from singular.validated_execution import ValidatedExecutionBoundary

    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)
    frontiere = ValidatedExecutionBoundary(moteur)

    with pytest.raises(PermissionError, match="fournisseur ou l'opération"):
        getattr(frontiere, chemin)(
            decision, decision.global_report.action_id, AUTHORIZED_PROVIDER,
            provider_name="autre-provider", operation="apply", payload=payload,
        )


def test_une_frontiere_sans_registre_d_attestation_refuse_d_exister():
    """Fail-closed a la construction : pas de registre, pas de frontiere.

    Le cas est celui d'un executeur qui n'est pas le moteur durable -- un double
    de test, un adaptateur maison. Sans registre ni base ou en deduire un, une
    frontiere construite quand meme n'aurait rien pour verifier l'attestation.
    """
    from singular.validated_execution import ValidatedExecutionBoundary

    class ExecuteurSansBase:
        pass

    with pytest.raises(TypeError, match="explicit DecisionAttestationStore"):
        ValidatedExecutionBoundary(ExecuteurSansBase())


def test_une_frontiere_dont_la_base_n_en_est_pas_une_refuse_aussi():
    """L'autre cas du meme garde, et le seul que quelque chose puisse distinguer.

    Un executeur peut porter un `store` qui n'est pas une base : un double de
    test, un adaptateur maison, un objet a moitie construit. Le garde le refuse
    parce qu'il n'a pas de `path` d'ou tirer un registre d'attestation -- et rien
    ne l'essayait. Le cas « aucun store du tout » etait joue, celui-la non, et la
    mutation par moities l'a nomme.
    """
    from singular.validated_execution import ValidatedExecutionBoundary

    class PasUneBase:
        """Il a tout d'un store, sauf ce dont la frontiere a besoin."""

        def get_execution(self, key):
            return None

    class ExecuteurAvecUnFauxStore:
        store = PasUneBase()

    with pytest.raises(TypeError, match="explicit DecisionAttestationStore"):
        ValidatedExecutionBoundary(ExecuteurAvecUnFauxStore())


# --- le coordinateur d'effets -------------------------------------------------

class FournisseurQuiTombe:
    """Il part, puis il casse : le cas ou personne ne sait si l'effet a eu lieu."""

    def __init__(self) -> None:
        self.appels = 0

    def execute(self, request, idempotency_key):
        self.appels += 1
        raise ConnectionResetError("la connexion est tombee apres l'envoi")

    def reconcile(self, request, idempotency_key):
        raise AssertionError("la reconciliation n'est pas ce qui est teste ici")


def test_un_effet_ambigu_ne_se_rejoue_pas_par_le_coordinateur(tmp_path):
    """Le refus qui empeche un deuxieme effet reel, et il n'avait pas de temoin.

    Le moteur traite deja l'ambiguite avant d'arriver ici -- il lit la ligne
    d'execution et rend RECOVERY_REQUIRED. Le coordinateur est public et son
    propre refus etait donc le seul garde d'un appelant direct : neutralise, la
    suite entiere restait verte, et un effet ambigu repartait vers le
    fournisseur. Sur un virement, c'est deux virements.
    """
    from singular.effects import EffectRequest
    from tests.support import claimed_execution_store

    store = claimed_execution_store(tmp_path / "effets.db")
    coordinateur = ExternalEffectCoordinator(store)
    requete = EffectRequest("execute-key", "provider", "write", {"montant": 42}, "action-fp")
    fournisseur = FournisseurQuiTombe()

    premier = coordinateur.execute(requete, fournisseur)
    assert premier.status == "UNKNOWN"
    assert fournisseur.appels == 1

    with pytest.raises(RuntimeError, match="réconciliation explicite"):
        coordinateur.execute(requete, fournisseur)

    assert fournisseur.appels == 1, "le fournisseur a ete rappele sur un effet ambigu"


# --- le registre durable de capacites -----------------------------------------

def test_une_capacite_ecrite_sous_un_autre_interpreteur_est_refusee(tmp_path):
    """L'empreinte d'artefact n'est pas comparable d'une version a l'autre.

    Le cas n'est pas theorique : le CI fait tourner 3.11 et 3.13, et une base
    durable ecrite par l'un peut etre relue par l'autre. `verify()` rend False
    dans ce cas -- teste -- mais `bind()`, qui est ce que le moteur appelle avant
    de rendre la main a l'executable, levait un refus que rien n'essayait.
    """
    from singular.execution_capability import DurableCapabilityStore

    registre = DurableCapabilityStore(tmp_path / "capacites.db")
    registre.bind("cap_temoin", authorized_handler)

    with registre._connect() as conn:
        conn.execute("UPDATE execution_capabilities SET runtime_version=? WHERE capability_id=?",
                     ("cpython-2.7", "cap_temoin"))

    with pytest.raises(PermissionError, match="different runtime version"):
        registre.bind("cap_temoin", authorized_handler)

    assert registre.verify("cap_temoin", authorized_handler) is False


# --- « exactement une fois », sur le chemin du handler ------------------------

def test_rejouer_une_decision_ne_relance_pas_le_handler(tmp_path):
    """Le README le promet ; la demo le prouve pour un effet, rien pour un handler.

    « Replaying a decision returns the first result without re-acting » : le
    compte d'appels au serveur de `examples/governed_http_effect.py` le montre
    pour un effet externe. Sur le chemin du handler, personne ne le regardait --
    `tests/support.py` tient `HANDLER_CALLS` depuis le debut pour cela, avec une
    docstring qui dit « so a suite can assert a replay did not re-run it », et
    aucune suite ne le faisait.

    Le temoin est partage par tout le paquet de tests : on mesure donc un
    **ecart**, pas une longueur. Une longueur serait vraie ou fausse selon les
    tests passes avant, et c'est exactement le defaut corrige ailleurs
    aujourd'hui -- un test qui ne passait que parce qu'il tournait en premier.

    Ce que ce test ne fait pas, dit ici pour que personne ne le croie : il ne
    pointe aucun mecanisme en particulier. Deux tiennent la promesse
    independamment -- la porte qui rend le premier resultat quand une execution
    existe deja, et l'echec de la reclamation durable derriere elle. Mesure en
    retirant la premiere : ces deux tests passent encore. Ils pointent donc la
    promesse du README, pas son implementation, et c'est ce qu'on veut d'eux.
    """
    from tests.support import HANDLER_CALLS, build_decision, support_handler

    decision = build_decision(decision_id="DEC-REJEU", mission_id="MIS-REJEU")
    moteur = _moteur(decision, tmp_path)
    avant = len(HANDLER_CALLS)

    premier = moteur.execute_validated(decision, support_handler)
    apres_un = len(HANDLER_CALLS)
    second = moteur.execute_validated(decision, support_handler)

    assert premier.status == "COMPLETED"
    assert second.status == "COMPLETED"
    assert second.result == premier.result, "le rejeu doit rendre le premier resultat"
    assert apres_un - avant == 1, "le premier appel doit avoir lance le handler une fois"
    assert len(HANDLER_CALLS) - avant == 1, "le rejeu a relance le handler"


def test_rejouer_une_decision_n_ecrit_pas_un_deuxieme_succes_dans_l_audit(tmp_path):
    """Deux COMPLETED pour une execution feraient croire a deux effets."""
    from tests.support import build_decision, support_handler

    decision = build_decision(decision_id="DEC-REJEU-AUDIT", mission_id="MIS-REJEU-AUDIT")
    moteur = _moteur(decision, tmp_path)

    moteur.execute_validated(decision, support_handler)
    moteur.execute_validated(decision, support_handler)

    succes = [evenement for evenement in moteur.store.audit_events()
              if evenement["event_type"] == "execution" and evenement["outcome"] == "COMPLETED"]
    assert len(succes) == 1, f"{len(succes)} succes enregistres pour une seule execution"
    assert moteur.store.verify_audit_integrity() is True


# --- ce que chaque moitie d'un garde compose garde ----------------------------
#
# `tools/gardes_sans_test.py` neutralise desormais **une moitie** a la fois d'un
# garde compose : `if a or b: raise` devient `if False or b: raise`, et l'autre
# moitie continue de garder. Un garde entier peut donc passer pour prouve alors
# qu'une de ses deux moities ne l'est pas. Le meme triage en trois familles
# s'applique, et il donne :
#
# * le garde de type des trois entrees validees : un trou. Sans lui,
#   `decision.verify()` part sur un objet quelconque.
# * le nom du fournisseur sur le chemin d'execution : un trou. La reconciliation
#   testait le fournisseur renomme, l'execution non -- et c'est l'execution qui
#   agit.
# * l'etat de la ligne d'execution avant une reconciliation : un trou. Les tests
#   n'essayaient que le cas « aucune ligne », jamais « une ligne, mais RUNNING ».
# * la gouvernance de la reconciliation : un trou. Le chemin d'execution avait
#   son contrat qui interdit l'action ; la reconciliation, non.
# * la moitie en memoire du controle de derniere seconde : un trou, le plus
#   etroit -- il faut revoquer dans la fenetre, et dans un seul des deux
#   registres.
# * `actual is None` a cote de `actual != expected` dans la liaison d'approbation :
#   rien ne produit leur entree. Une decision validee ne porte pas ESCALATE, donc
#   aucune execution validee ne passe par une approbation -- meme famille que les
#   quatre refus d'approbation deja triés ici. (Le meme couple existe pour
#   l'identite d'execution, lui, et il a deja deux temoins.)
# * le prefixe `cap_` des trois memes entrees : rien ne produit leur entree, et
#   le test ci-dessous le prouve au lieu de l'affirmer.
# * dans l'adaptateur, `not expected_target` a cote de la comparaison des cibles :
#   meme famille. `_validated_action` verifie la decision avant, et une decision
#   d'effet qui passe `verify()` porte forcement un `provider_target` -- son
#   `_validate` l'exige. La moitie garde un objet qui n'a pas ete verifie, et il
#   n'y a pas de chemin qui en presente un.
# * `store is None` a cote de `not hasattr(store, "path")` : celle-la n'etait ni
#   un trou ni une assurance, elle etait **morte** -- `hasattr(None, "path")` est
#   faux, donc la seconde moitie refusait deja. Retiree, et l'autre moitie a
#   maintenant son temoin.
# * `mode == BLOCK` et `not governed.can_prepare`, dans les deux copies du garde
#   de gouvernance : les deux moities sont co-extensives, et c'est mesure. Les
#   trois producteurs de BLOCK -- `RedTeamGate` bloquant, une politique qui
#   refuse la preparation, `_blocked` du runtime -- rendent tous les trois
#   `can_prepare=False` en meme temps, et le gouverneur BLOCK du bus est
#   inatteignable parce que le red team bloque avant lui. Aucune entree ne
#   distingue donc les deux moities : on ne peut prouver que le garde entier,
#   et c'est ce que fait le test de la reconciliation ci-dessous.


@pytest.mark.parametrize("faux", [None, object(), "DEC-DEMO", 42, {"decision_id": "DEC-X"}])
def test_le_moteur_refuse_ce_qui_n_est_pas_une_decision(tmp_path, faux):
    """Les trois entrees validees ont le meme garde de type, et personne ne l'essayait.

    Sans lui, `decision.verify()` part sur un objet quelconque et leve
    `AttributeError` : un accident, pas un refus. Un appelant qui rattrape
    `PermissionError` -- ce que fait la frontiere elle-meme -- ne le verrait pas
    venir.
    """
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="missing or invalid"):
        moteur.execute_validated(faux, authorized_handler)
    with pytest.raises(PermissionError, match="missing or invalid"):
        moteur.execute_effect_validated(faux, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
                                        operation="apply", payload=payload)
    with pytest.raises(PermissionError, match="missing or invalid"):
        moteur.reconcile_effect_validated(faux, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
                                          operation="apply", payload=payload)


def test_aucune_decision_ne_peut_nommer_une_cible_sans_prefixe():
    """Pourquoi le prefixe `cap_` de la frontiere est une assurance, mesure ici.

    Trois entrees validees exigent `execution_target.startswith("cap_")`, et la
    mutation dit que ce refus ne tue aucun test. Ce n'est pas un trou : une
    decision qui porterait une telle cible n'existe pas. Mais « n'existe pas »
    se prouve, sinon c'est une croyance -- donc les trois portes sont essayees.

    Le registre etait la seule des trois a laisser passer : il frappait un jeton
    qu'aucune decision ne pourrait jamais nommer, et que la frontiere refusait
    donc toujours, le plus tard possible. Un jeton inutilisable n'a pas a etre
    frappable ; la regle vit maintenant la ou le jeton nait.
    """
    from singular.autopilot import ActionRequest
    from singular.execution_capability import ExecutionCapabilityRegistry

    def executable(action):
        return {"action_id": action.id}

    with pytest.raises(ValueError, match="opaque cap_ token"):
        ActionRequest("une_action", "une action", 4, 1, 9, contract_id="MIS-X",
                      execution_capability="pas_une_capacite")

    with pytest.raises(ValueError, match="opaque execution capability"):
        build_decision(decision_id="DEC-SANS-PREFIXE", mission_id="MIS-SANS-PREFIXE",
                       execution_target="pas_une_capacite")

    with pytest.raises(ValueError, match="opaque cap_ token"):
        ExecutionCapabilityRegistry().register(executable, "pas_une_capacite")


def test_l_execution_d_un_effet_refuse_un_fournisseur_renomme(tmp_path):
    """Le meme nom que la decision, ou rien -- sur le chemin qui agit.

    `reconcile_effect_validated` etait teste avec un fournisseur renomme ;
    `execute_effect_validated`, non : seule l'operation substituee etait
    essayee. Les deux moities vivent dans la meme ligne, donc le garde entier
    passait pour prouve. Le nom du fournisseur decide de quel cote du reseau
    part l'effet.
    """
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)

    with pytest.raises(PermissionError, match="Provider or operation"):
        moteur.execute_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="autre-provider",
            operation="apply", payload=payload,
        )


def test_la_reconciliation_refuse_une_execution_qui_n_est_pas_en_recuperation(tmp_path):
    """Une ligne existe, mais pas dans l'etat qui autorise une reconciliation.

    Le seul cas joue etait « aucune ligne du tout ». Celui-ci est l'autre moitie
    du meme garde, et c'est le dangereux : une execution RUNNING appartient a un
    bail que quelqu'un detient. Reconcilier par-dessus irait demander a un
    fournisseur ce qu'il a fait d'un effet dont un autre ouvrier repond encore,
    et pourrait ecrire un etat terminal sous lui.

    `AUTHORIZED_PROVIDER` leve si on l'appelle : le test prouve donc aussi que
    le refus arrive avant le reseau.
    """
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)
    mission = decision.contract.mission_id
    action_id = decision.global_report.action_id
    cle = moteur.store.idempotency_key("execute", mission, action_id)
    moteur.store.set_mission_status(mission, MissionStatus.PLANNED)
    moteur.store.begin_execution_and_start_mission(cle, mission, action_id, lease_seconds=300)
    assert moteur.store.get_execution(cle)["status"] == "RUNNING"

    with pytest.raises(ValueError, match="RECOVERY_REQUIRED"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


def test_la_reconciliation_refuse_une_action_que_le_contrat_interdit_desormais(tmp_path):
    """La gouvernance de la reconciliation, que le chemin d'execution avait seul.

    `_authorize_reconciliation` a le meme premier garde que `_validate_governance`,
    et une seule des deux copies etait exercee : une interdiction arrivee apres
    l'emission bloquait l'execution et pas la reconciliation, qui atteint le meme
    fournisseur.

    Ce test tue le garde entier, pas une de ses moities : une action interdite
    fait bloquer le red team, qui rend `BLOCK` **et** `can_prepare=False` dans le
    meme objet. C'est pour cela que la passe par moities ne peut rien prouver
    ici, et que ce temoin-la est le bon niveau.
    """
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)
    _altere_le_contrat_durable(moteur.store, decision.contract.mission_id,
                               forbidden_actions=[decision.authorized_actions[0].name])

    with pytest.raises(PermissionError, match="bloquée par la gouvernance"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )


def test_une_revocation_en_memoire_seule_arrete_l_execution(tmp_path):
    """La moitie en memoire du controle de derniere seconde, que rien n'essayait.

    Le moteur relit deux registres juste avant de rendre la main a l'executable :
    celui en memoire -- cet objet exactement, cette empreinte -- et le durable,
    qui survit au restart. Les tests de revocation dans la fenetre revoquaient
    toujours le **durable**, donc la moitie en memoire pouvait disparaitre sans
    qu'un test rougisse.

    Les deux ne disent pas la meme chose. `revoke` sur le registre global n'a pas
    de base derriere lui -- rien n'appelle `set_durable` -- donc il retire le
    jeton d'ici et laisse l'enregistrement durable du moteur ACTIF. Il faut alors
    que la moitie en memoire refuse, sinon un jeton retire continue d'executer.

    Revoquer avant l'appel ne prouverait rien de ce controle : le garde du haut
    refuserait d'abord. La revocation se fait donc dans la fenetre, comme la vraie.

    Le jeton et l'executable sont jetables, crees pour ce test seul : revoquer un
    jeton partage casserait les tests suivants selon l'ordre.
    """
    from singular.execution_capability import (
        GLOBAL_EXECUTION_CAPABILITIES,
        register_execution_capability,
    )

    def executable_jetable(action):
        return {"action_id": action.id, "executed": True}

    jeton = register_execution_capability(executable_jetable, "cap_revoquee_en_memoire")
    decision = build_decision(decision_id="DEC-REVOC-MEM", mission_id="MIS-REVOC-MEM",
                              execution_target=jeton)
    moteur = _moteur(decision, tmp_path)
    _pendant(moteur, "_authorize", lambda: GLOBAL_EXECUTION_CAPABILITIES.revoke(jeton))

    with pytest.raises(PermissionError, match="n'est plus valide"):
        moteur.execute_validated(decision, executable_jetable)

    # Ce qui isole la moitie testee : le durable, lui, dit encore oui.
    assert moteur.capability_store.verify(jeton, executable_jetable) is True


def test_un_mode_d_autonomie_qui_n_execute_pas_est_refuse(tmp_path):
    """La derniere porte sur le mode, et elle n'avait aucun temoin.

    `_validate_governance` rejette BLOCK, puis PREPARE, puis verifie que le mode
    est bien l'un des trois qui executent. `Autonomy` en compte **sept** :
    OBSERVE et ANALYZE ne sont rejetes par aucun des gardes precedents, et
    `can_execute` vient de la politique -- risque et reversibilite -- pas du
    mode. Une action verte en mode OBSERVE passe donc les trois premiers gardes,
    et seule cette ligne-ci l'arrete.

    `Governor.evaluate` n'emet jamais ces deux modes aujourd'hui. Mais
    `_from_cached` reconstruit le mode depuis la base -- `Autonomy(cached["mode"])`
    -- donc une ligne de gouvernance persistee par une autre version, ou abimee,
    arrive ici avec le mode qu'elle porte. C'est exactement la « stale policy »
    et les « anciennes donnees persistees » que le mandat demande de chercher, et
    ce garde est ce qui les refuse.
    """
    from singular.autopilot import ActionRequest, Autonomy, GovernorDecision
    from singular.v32_governed_core import GovernedAction

    engine = DurableExecutionEngine(DurableMissionRuntime(DurableStore(tmp_path / "d.db")))
    action = ActionRequest("lire_fichier", "une action verte", 1, 9, 9, contract_id="MIS-MODE")

    for mode in (Autonomy.OBSERVE, Autonomy.ANALYZE):
        governed = GovernedAction(
            action, "GREEN", GovernorDecision(action.id, mode, ()),
            can_prepare=True, can_execute=True, requires_human=False,
            reasons=("etat venu du disque",),
        )
        with pytest.raises(PermissionError, match="non exécutable"):
            engine._validate_governance(governed, action, "MIS-MODE")


def test_une_gouvernance_qui_prepare_sans_executer_est_refusee(tmp_path):
    """Preparer n'est pas executer, et aucune politique ne les separe aujourd'hui.

    Les sept `PolicyDecision` du depot rendent toutes `(False, False)` ou
    `(True, True)` : `can_prepare` et `can_execute` sont donc toujours egaux, et
    le garde precedent -- `not can_prepare` -- couvre celui-ci. C'est pour ca
    qu'aucun test ne l'atteignait.

    Il reste atteignable par le disque : `_from_cached` relit les deux champs
    **separement**, donc une ligne ou ils ne s'accordent pas arrive ici telle
    quelle. Le refus est ce qui empeche « prepare » de valoir « execute » apres
    un redemarrage.
    """
    from singular.autopilot import ActionRequest, Autonomy, GovernorDecision
    from singular.v32_governed_core import GovernedAction

    engine = DurableExecutionEngine(DurableMissionRuntime(DurableStore(tmp_path / "d.db")))
    action = ActionRequest("lire_fichier", "une action verte", 1, 9, 9, contract_id="MIS-PREP")
    governed = GovernedAction(
        action, "GREEN", GovernorDecision(action.id, Autonomy.EXECUTE_REVERSIBLE, ()),
        can_prepare=True, can_execute=False, requires_human=False,
        reasons=("etat venu du disque",),
    )
    with pytest.raises(PermissionError, match="non autorisée à l'exécution"):
        engine._validate_governance(governed, action, "MIS-PREP")



def test_un_contrat_retrograde_a_prepare_tombe_avant_la_comparaison_de_gouverneur(tmp_path):
    """Retrograde, pas seulement change : c'est un autre garde qui refuse.

    Le test voisin altere l'autonomie vers EXECUTE_AUTHORIZED, ce qui fait
    diverger le gouverneur et tombe sur « governance no longer matches ». Vers
    PREPARE, on ne va pas si loin : `_authorize` recalcule la gouvernance
    **avant** cette comparaison -- l'ordre des lignes de `execute_validated` le
    montre -- et `_validate_governance` refuse des qu'il voit le mode PREPARE.

    Les deux gardes vivent donc sur le meme chemin et seul le premier etait
    joue. Celui-ci est celui qui dit « preparee mais non autorisee a
    l'execution » : c'est la difference entre un contrat qui a change et un
    contrat qui a **perdu** le droit d'executer, et c'est la seconde qui est la
    « stale authorization » de la section 7 du mandat.
    """
    decision = _build_decision()
    moteur = _moteur(decision, tmp_path)
    _altere_le_contrat_durable(moteur.store, decision.contract.mission_id,
                               autonomy=Autonomy.PREPARE.value)

    with pytest.raises(PermissionError, match="préparée mais non autorisée"):
        moteur.execute_validated(decision, authorized_handler)


def test_un_contrat_altere_refuse_aussi_la_reconciliation(tmp_path):
    """Teste a l'aller, jamais au retour -- et c'est le retour qui conclut l'effet.

    Les deux tests voisins jouent la derive de gouvernance sur
    `execute_validated` et `execute_effect_validated`. `reconcile_effect_validated`
    porte le meme garde, a la meme place, et personne ne l'essayait. L'audit de
    mutation l'a nomme.

    Ce chemin-la est le plus dangereux des trois a laisser sans temoin : la
    reconciliation ne demande pas au monde d'agir, elle **conclut** ce qui a
    peut-etre deja agi -- elle fait passer une execution a COMPLETED. Une
    autorisation perimee qui franchirait ce garde ne declencherait rien de
    nouveau ; elle graverait comme acquis un effet que plus personne n'autorise.
    """
    decision, payload = _build_effect_decision()
    moteur = _moteur(decision, tmp_path)
    _altere_le_contrat_durable(moteur.store, decision.contract.mission_id,
                               autonomy=Autonomy.EXECUTE_AUTHORIZED.value)

    with pytest.raises(PermissionError, match="governance no longer matches"):
        moteur.reconcile_effect_validated(
            decision, AUTHORIZED_PROVIDER, provider_name="bounded-provider",
            operation="apply", payload=payload,
        )
