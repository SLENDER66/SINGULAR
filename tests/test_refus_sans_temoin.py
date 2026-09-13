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
from singular.durable import DurableStore
from singular.effects import ExternalEffectCoordinator
from singular.execution import DurableExecutionEngine
from singular.mission_runtime import DurableMissionRuntime
from singular.security import ActionPolicy
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
