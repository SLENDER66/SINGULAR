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
import threading
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest

from singular.journal import DecisionJournal, Tier
from singular.sage.server import SageApp, SageError, build_server


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


# --- le credit achete, qui ne repart pas le lendemain -------------------------

def test_l_etat_porte_le_bilan_de_depense(app, sans_cle) -> None:
    """Gratuit, sans clé : savoir ce qu'on a dépensé ne doit rien coûter."""
    etat = app.parle_etat()
    assert "bilan" in etat
    assert etat["usd"] is None, "aucun tarif n'a été donné : aucun montant ne doit sortir"


def test_un_tour_ajoute_sa_depense_au_total(app, client) -> None:
    from singular import parle

    app.parle({"question": "une"})
    app.parle({"question": "deux"})

    depenses = parle.Quota().depenses()
    modele = next(iter(depenses))
    assert depenses[modele]["entree"] == 200, "les deux tours n'ont pas été additionnés"


def test_le_total_survit_au_lendemain_et_au_redemarrage(app, client, monkeypatch) -> None:
    """Le plafond est quotidien ; les cinq dollars achetés ne le sont pas.

    Respecter le plafond tous les jours et vider le crédit sans le voir venir
    est exactement ce que ce total empêche.
    """
    from singular import parle

    app.parle({"question": "une"})
    quota = parle.Quota()
    quota._ecrire({**quota._lire(), "jour": "1970-01-01"})  # comme si un jour passait

    autre = SageApp(app.journal, token="jeton")
    etat = autre.parle_etat()
    assert etat["restants"] == etat["plafond"], "le plafond n'a pas repris"
    assert parle.Quota().depenses(), "le total de dépense a été effacé"


def test_le_montant_apparait_des_qu_il_donne_ses_tarifs(app, client, tmp_path, monkeypatch) -> None:
    """Ce dépôt n'écrit aucun prix. Les siens font apparaître les dollars."""
    import json

    from singular import parle

    app.parle({"question": "une"})
    modele = next(iter(parle.Quota().depenses()))
    (tmp_path / "tarifs.json").write_text(json.dumps({
        "credit_usd": 5.0,
        "modeles": {modele: {"entree": 3.0, "sortie": 15.0,
                             "cache_lu": 0.3, "cache_ecrit": 3.75}},
    }), encoding="utf-8")
    monkeypatch.setattr(parle, "FICHIER_TARIFS", tmp_path / "tarifs.json")

    etat = app.parle_etat()
    assert etat["usd"] is not None
    assert etat["restant_usd"] is not None
    assert "$" in etat["bilan"]


def test_le_credit_epuise_refuse_avant_d_appeler(app, client, tmp_path, monkeypatch) -> None:
    """La vraie garde. Le service refuserait de toute façon, une requête plus
    tard et sans le dire aussi clairement."""
    import json

    from singular import parle

    app.parle({"question": "une"})
    modele = next(iter(parle.Quota().depenses()))
    (tmp_path / "tarifs.json").write_text(json.dumps({
        "credit_usd": 0.0, "modeles": {modele: {"entree": 3.0}},
    }), encoding="utf-8")
    monkeypatch.setattr(parle, "FICHIER_TARIFS", tmp_path / "tarifs.json")

    appels_avant = client.appels
    with pytest.raises(SageError) as refus:
        app.parle({"question": "deux"})
    assert refus.value.status == HTTPStatus.PAYMENT_REQUIRED
    assert client.appels == appels_avant, "le service a été appelé alors que le crédit est vide"
    assert "credit_usd" in str(refus.value.message)


def test_sans_tarifs_le_credit_ne_refuse_jamais(app, client) -> None:
    """Il n'a rien écrit : deviner qu'il est à sec le couperait sans raison."""
    for numero in range(3):
        assert app.parle({"question": f"question {numero}"})["reponse"]


# --- le chemin reel du telephone ----------------------------------------------
#
# Tout ce qui precede appelle `SageApp` directement. Le telephone, lui, passe
# par HTTP : l'authentification, la garde contre les autres pages, le type du
# corps. C'est le chemin qu'il va emprunter, donc c'est celui qu'il faut avoir
# essaye avant lui.

@pytest.fixture
def tournant(app):
    serveur = build_server(app, "127.0.0.1", 0)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()
    serveur.server_close()


def _demander(base: str, chemin: str, corps: dict | None = None, **entetes) -> tuple[int, dict]:
    requete = urllib.request.Request(
        base + chemin,
        data=json.dumps(corps).encode() if corps is not None else None,
        method="POST" if corps is not None else "GET",
        headers={"Content-Type": "application/json", **entetes},
    )
    try:
        with urllib.request.urlopen(requete, timeout=5) as reponse:
            return reponse.status, json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as refus:
        return refus.code, json.loads(refus.read().decode("utf-8"))


def test_le_fil_se_lit_par_http(tournant, sans_cle) -> None:
    statut, rendu = _demander(tournant, "/api/parle")
    assert statut == 200
    assert rendu["tours"] == []
    assert rendu["plafond"] > 0


def test_un_tour_complet_par_http(tournant, client) -> None:
    """La chaine entiere, telle que le telephone la parcourt."""
    statut, rendu = _demander(tournant, "/api/parle", {"question": "je fais quoi ?"})
    assert statut == 200, rendu
    assert rendu["reponse"] == "Voilà."

    _, etat = _demander(tournant, "/api/parle")
    assert [t["content"] for t in etat["tours"]] == ["je fais quoi ?", "Voilà."]


def test_la_faculte_coupee_repond_503_et_pas_une_pile(tournant, sans_cle) -> None:
    """Ce qui remonte doit etre une phrase, pas une trace technique."""
    statut, rendu = _demander(tournant, "/api/parle", {"question": "et alors ?"})
    assert statut == HTTPStatus.SERVICE_UNAVAILABLE
    assert "ANTHROPIC_API_KEY" in rendu["message"]
    assert "Traceback" not in rendu["message"]


def test_une_autre_page_ne_peut_pas_depenser_son_credit(tournant, client) -> None:
    """La menace a laquelle cette route ajoute un enjeu : une page web ouverte
    sur le PC pouvait ecrire dans le journal ; elle pourrait maintenant vider
    cinq dollars, sans rien afficher et sans connaitre le jeton.

    Les trois memes faits la refusent -- l'origine declaree, le nom par lequel
    on nous appelle, le type du corps -- et il faut le verifier ici plutot que
    d'esperer que la garde couvre les routes ajoutees apres elle.
    """
    statut, _ = _demander(tournant, "/api/parle", {"question": "vide sa poche"},
                          Origin="https://exemple.invalide")
    assert statut == HTTPStatus.FORBIDDEN
    assert client.appels == 0, "une autre page a fait payer une requete"


def test_un_corps_non_json_ne_peut_pas_declencher_une_depense(tournant, client) -> None:
    """Le type du corps est ce qu'une page ne peut pas choisir librement sans
    demander une permission que ce serveur ne donne pas."""
    requete = urllib.request.Request(
        tournant + "/api/parle", data=b"question=vide+sa+poche", method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=5) as reponse:
            statut = reponse.status
    except urllib.error.HTTPError as refus:
        statut = refus.code

    assert statut == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert client.appels == 0


def test_oublier_par_http_n_efface_que_le_fil(tournant, client) -> None:
    _demander(tournant, "/api/parle", {"question": "une"})
    statut, rendu = _demander(tournant, "/api/parle/oubli", {})

    assert statut == 200
    assert rendu["tours"] == []
    assert len(app_entries(tournant)) == 1


def app_entries(base: str) -> list:
    _, rendu = _demander(base, "/api/entries")
    return rendu["entries"]


# --- ce que le demarrage annonce ----------------------------------------------

def test_le_demarrage_dit_si_la_conversation_est_coupee(monkeypatch) -> None:
    """Une clé oubliée ne se découvre sinon qu'une fois le téléphone en main,
    loin du clavier — et la commande qui la pose n'est pas la même en `cmd`
    et en PowerShell."""
    from singular.parle import etat_de_la_faculte

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    allumee, phrase = etat_de_la_faculte()
    assert allumee is False
    assert "ANTHROPIC_API_KEY" in phrase


def test_le_demarrage_dit_le_modele_et_le_plafond(monkeypatch) -> None:
    from singular.parle import MODELE_PAR_DEFAUT, PLAFOND_PAR_JOUR, etat_de_la_faculte

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-peu-importe")
    allumee, phrase = etat_de_la_faculte()
    assert allumee is True
    assert MODELE_PAR_DEFAUT in phrase
    assert str(PLAFOND_PAR_JOUR) in phrase


def test_le_demarrage_ne_montre_jamais_la_cle(monkeypatch) -> None:
    """La phrase est affichée dans une console, parfois recopiée ailleurs."""
    from singular.parle import etat_de_la_faculte

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SENTINELLE")
    assert "SENTINELLE" not in etat_de_la_faculte()[1]


def test_le_sage_annonce_l_etat_sans_le_nommer_lui_meme() -> None:
    """Le Sage n'a pas le droit d'écrire le nom d'une variable de clé — un test
    d'indépendance le lui interdit. La phrase vient donc de la faculté, et
    l'import est dans la fonction pour que le serveur marche sans elle."""
    import ast
    import pathlib

    source = pathlib.Path("singular/sage/server.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    dans_serve = [n for n in ast.walk(arbre)
                  if isinstance(n, ast.FunctionDef) and n.name == "serve"]
    assert dans_serve, "la fonction serve() a disparu"
    assert any(isinstance(n, ast.ImportFrom) and "parle" in (n.module or "")
               for n in ast.walk(dans_serve[0])), "l'import a quitté la fonction"
