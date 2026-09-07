"""La conversation servie depuis le téléphone : ce qu'elle coûte, et ses refus.

C'est la première route du Sage qui peut dépenser de l'argent. Tout ce fichier
tourne autour de cette phrase : ce qui refuse doit refuser avant la dépense, ce
qui est coupé doit être coupé sans rien emporter, et le reste de l'app doit
continuer quand cette faculté ne répond pas.

Aucun test ici n'appelle un service. Le client est injecté, ou la faculté est
coupée -- un test qui appellerait le vrai modèle testerait la météo et coûterait
de l'argent à chaque exécution du CI.
"""
from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage.server import SageApp, SageError


@pytest.fixture
def app(tmp_path, monkeypatch) -> SageApp:
    """Un Sage complet, avec le fil et le compteur dans un dossier jetable."""
    from singular import parle

    monkeypatch.setattr(parle, "FICHIER", tmp_path / "conversation.json")
    monkeypatch.setattr(parle, "FICHIER_QUOTA", tmp_path / "quota.json")

    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(title="Postuler", action="candidature", predicted="un entretien",
                probability=0.5, tier=Tier.REVENUS, cost_hours=3, horizon_days=14)
    return SageApp(journal, token="jeton")


@pytest.fixture
def sans_cle(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# --- ce qui marche sans clé et sans réseau -----------------------------------

def test_l_etat_du_fil_ne_coute_rien(app, sans_cle) -> None:
    """Rouvrir l'app doit montrer la conversation d'hier, sans rien dépenser."""
    etat = app.parle_etat()
    assert etat["tours"] == []
    assert etat["restants"] == etat["plafond"] > 0


def test_le_reste_de_l_app_marche_quand_la_faculte_est_coupee(app, sans_cle) -> None:
    """L'invariant du dépôt : une faculté qui a besoin d'un modèle doit pouvoir
    être coupée sans rien casser d'autre. Vérifié sur l'acte."""
    with pytest.raises(SageError) as refus:
        app.parle({"question": "et alors ?"})
    assert refus.value.status == HTTPStatus.SERVICE_UNAVAILABLE

    assert app.notice()["headline"]
    assert len(app.entries()["entries"]) == 1
    ajoutee = app.add({
        "title": "Relancer", "action": "un mail", "predicted": "une réponse",
        "probability": 0.4, "tier": Tier.REVENUS.value, "cost_hours": 1, "horizon_days": 7,
    })
    assert ajoutee["entry_id"]
    assert app.journal.verify() is True


def test_une_faculte_coupee_ne_consomme_pas_le_plafond(app, sans_cle) -> None:
    """Sinon une clé oubliée coûterait la journée."""
    avant = app.parle_etat()["restants"]
    for _ in range(3):
        with pytest.raises(SageError):
            app.parle({"question": "et alors ?"})
    assert app.parle_etat()["restants"] == avant


# --- ce qui refuse avant la dépense -------------------------------------------

def test_une_question_vide_est_refusee(app) -> None:
    with pytest.raises(SageError) as refus:
        app.parle({"question": "   "})
    assert refus.value.status == HTTPStatus.BAD_REQUEST


def test_une_question_demesuree_est_refusee(app) -> None:
    """Elle partirait vers un service qui facture ce qu'on lui envoie."""
    from singular.sage.server import QUESTION_MAX

    with pytest.raises(SageError) as refus:
        app.parle({"question": "a" * (QUESTION_MAX + 1)})
    assert refus.value.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_un_seul_tour_a_la_fois(app) -> None:
    """Deux tours simultanés feraient deux factures pour une question, et la
    seconde écriture du fil écraserait la première."""
    app._un_tour.acquire()
    try:
        with pytest.raises(SageError) as refus:
            app.parle({"question": "et alors ?"})
        assert refus.value.status == HTTPStatus.CONFLICT
    finally:
        app._un_tour.release()


def test_le_verrou_est_rendu_meme_quand_la_faculte_refuse(app, sans_cle) -> None:
    """Sinon la première panne fermerait la conversation jusqu'au redémarrage."""
    with pytest.raises(SageError):
        app.parle({"question": "et alors ?"})
    assert app._un_tour.acquire(blocking=False), "le verrou n'a pas été rendu"
    app._un_tour.release()


# --- le plafond ---------------------------------------------------------------

class FauxBloc:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FausseConso:
    input_tokens = 100
    output_tokens = 30
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class FausseReponse:
    def __init__(self) -> None:
        self.content = [FauxBloc("Voilà.")]
        self.stop_reason = "end_turn"
        self.usage = FausseConso()


class FauxClient:
    def __init__(self) -> None:
        self.appels = 0

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.appels += 1
        return FausseReponse()


@pytest.fixture
def client(monkeypatch) -> FauxClient:
    """Le SDK remplacé au point où le serveur l'appelle."""
    from singular import parle

    faux = FauxClient()
    vrai = parle.repondre

    def injecte(question, contexte, conversation, *, modele=None, client=None):
        return vrai(question, contexte, conversation, modele=modele, client=client or faux)

    monkeypatch.setattr(parle, "repondre", injecte)
    return faux


def test_un_tour_rend_la_reponse_et_ce_qu_il_reste(app, client) -> None:
    plafond = app.parle_etat()["plafond"]
    rendu = app.parle({"question": "je fais quoi ?"})
    assert rendu["reponse"] == "Voilà."
    assert rendu["restants"] == plafond - 1
    assert rendu["cout"]["entree"] == 100


def test_le_fil_survit_d_un_tour_a_l_autre(app, client) -> None:
    app.parle({"question": "première"})
    app.parle({"question": "seconde"})
    tours = app.parle_etat()["tours"]
    assert [t["content"] for t in tours][:3] == ["première", "Voilà.", "seconde"]


def test_le_plafond_refuse_le_tour_suivant(app, client, monkeypatch) -> None:
    from singular import parle

    monkeypatch.setattr(parle, "PLAFOND_PAR_JOUR", 2)

    app.parle({"question": "une"})
    app.parle({"question": "deux"})
    with pytest.raises(SageError) as refus:
        app.parle({"question": "trois"})
    assert refus.value.status == HTTPStatus.TOO_MANY_REQUESTS
    assert client.appels == 2, "le troisième tour a quand même été facturé"


def test_le_plafond_survit_au_redemarrage(app, client, monkeypatch, tmp_path) -> None:
    """Un plafond qu'un redémarrage efface n'est pas un plafond."""
    from singular import parle

    monkeypatch.setattr(parle, "PLAFOND_PAR_JOUR", 1)
    app.parle({"question": "une"})

    autre = SageApp(app.journal, token="jeton")  # comme après un redémarrage
    with pytest.raises(SageError) as refus:
        autre.parle({"question": "deux"})
    assert refus.value.status == HTTPStatus.TOO_MANY_REQUESTS


def test_le_plafond_repart_le_lendemain(app, client, monkeypatch, tmp_path) -> None:
    from singular import parle

    quota = parle.Quota(tmp_path / "quota.json", plafond=1)
    quota.consommer(aujourdhui="2026-09-07")
    assert quota.restants(aujourdhui="2026-09-07") == 0
    assert quota.restants(aujourdhui="2026-09-08") == 1


def test_un_compteur_illisible_ne_ferme_pas_la_conversation(tmp_path) -> None:
    """L'écriture est atomique, donc un fichier cassé n'est pas une écriture
    interrompue : c'est un premier lancement, ou un effacement volontaire."""
    from singular import parle

    chemin = tmp_path / "quota.json"
    chemin.write_text("{ceci n'est pas du json", encoding="utf-8")
    assert parle.Quota(chemin, plafond=5).restants() == 5


def test_le_compteur_est_ecrit_atomiquement(tmp_path) -> None:
    """Rien de provisoire ne doit rester à côté du compteur."""
    from singular import parle

    quota = parle.Quota(tmp_path / "quota.json", plafond=5)
    quota.consommer()
    assert json.loads((tmp_path / "quota.json").read_text(encoding="utf-8"))["tours"] == 1
    assert not (tmp_path / "quota.tmp").exists()


# --- oublier ------------------------------------------------------------------

def test_oublier_efface_le_fil_et_pas_le_journal(app, client) -> None:
    app.parle({"question": "une"})
    assert app.parle_etat()["tours"]

    apres = app.parle_oubli()
    assert apres["tours"] == []
    assert len(app.entries()["entries"]) == 1
    assert app.journal.verify() is True


def test_oublier_ne_rend_pas_le_plafond(app, client) -> None:
    """Sinon effacer le fil serait le moyen de dépenser sans limite."""
    plafond = app.parle_etat()["plafond"]
    app.parle({"question": "une"})
    assert app.parle_oubli()["restants"] == plafond - 1


# --- le routage ---------------------------------------------------------------

def test_les_routes_sont_branchees(app, client) -> None:
    assert app.route("GET", "/api/parle", {}, {})["tours"] == []
    assert app.route("POST", "/api/parle", {}, {"question": "salut"})["reponse"] == "Voilà."
    assert app.route("POST", "/api/parle/oubli", {}, {})["tours"] == []


def test_une_route_de_conversation_inconnue_est_refusee(app) -> None:
    with pytest.raises(SageError) as refus:
        app.route("POST", "/api/parle/tout-effacer", {}, {})
    assert refus.value.status == HTTPStatus.NOT_FOUND


def test_une_reponse_payee_n_est_pas_perdue_pour_un_compteur(app, client, monkeypatch) -> None:
    """Le compteur peut se remplir entre la vérification et le décompte : un
    second serveur sur la même machine, ou la ligne de commande.

    La réponse est déjà payée et déjà écrite dans le fil. La perdre pour un
    compteur serait le seul vrai dégât de la situation.
    """
    from singular import parle

    def plein(self, **kwargs):
        raise parle.PlafondAtteint("rempli entre-temps")

    monkeypatch.setattr(parle.Quota, "consommer", plein)
    rendu = app.parle({"question": "et alors ?"})
    assert rendu["reponse"] == "Voilà."
    assert rendu["restants"] == 0
    assert app.parle_etat()["tours"], "le fil a perdu le tour payé"
