"""Le bouton 🔎 : ce qu'il cherche, ce qu'il refuse, et ce qu'il ne fera jamais.

La seconde route du Sage qui dépense, et la plus chère : une recherche web
ramène des pages entières, là où un tour de conversation ne renvoie que le fil.
Elle est donc tenue par les mêmes gardes que `parle`, plus une qui lui est
propre — elle ne postule pas, et ça se vérifie sur ce qu'elle peut atteindre,
pas sur ce que son instruction lui demande. Une consigne se contourne par une
tournure de phrase ; une absence d'accès, non.

Aucun test ici n'appelle un service : le client est injecté, ou la faculté est
coupée. Un test qui appellerait le vrai modèle testerait la météo et coûterait
de l'argent à chaque exécution du CI.
"""
from __future__ import annotations

from http import HTTPStatus

import pytest

from singular.journal import DecisionJournal, Status, Tier
from singular.sage.server import SageApp, SageError


@pytest.fixture
def app(tmp_path, monkeypatch) -> SageApp:
    from singular import parle

    monkeypatch.setattr(parle, "FICHIER", tmp_path / "conversation.json")
    monkeypatch.setattr(parle, "FICHIER_QUOTA", tmp_path / "quota.json")

    journal = DecisionJournal(tmp_path / "journal.db")
    journal.add(title="Postuler", action="candidature", predicted="un entretien",
                probability=0.75, tier=Tier.REVENUS, cost_hours=4, horizon_days=14)
    return SageApp(journal, token="jeton")


@pytest.fixture
def sans_cle(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class FauxBloc:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FausseConso:
    input_tokens = 9000
    output_tokens = 1200
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class FausseReponse:
    def __init__(self) -> None:
        self.content = [FauxBloc("1. Chargé d'études CVC — https://exemple.fr/1")]
        self.stop_reason = "end_turn"
        self.usage = FausseConso()


class FauxClient:
    def __init__(self) -> None:
        self.appels: list[dict] = []

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return FausseReponse()


@pytest.fixture
def client(monkeypatch) -> FauxClient:
    """Le SDK remplacé au point où le serveur l'appelle."""
    from singular import offres

    faux = FauxClient()
    vrai = offres.chercher

    def injecte(question="", *, modele=None, client=None):
        return vrai(question, modele=modele, client=client or faux)

    monkeypatch.setattr(offres, "chercher", injecte)
    return faux


# --- ce qui marche sans clé et sans réseau -----------------------------------

def test_voir_ce_qui_partirait_ne_coute_rien(app, sans_cle) -> None:
    """Il a le droit de relire ce qui est dit de lui avant que ça parte."""
    etat = app.offres_etat()
    assert "bureau d'etudes CVC" in etat["contexte"]
    assert etat["restants"] == etat["plafond"] > 0


def test_le_reste_de_l_app_marche_quand_la_recherche_est_coupee(app, sans_cle) -> None:
    with pytest.raises(SageError) as refus:
        app.offres({})
    assert refus.value.status == HTTPStatus.SERVICE_UNAVAILABLE

    assert app.notice()["headline"]
    assert len(app.entries()["entries"]) == 1
    assert app.journal.verify() is True


def test_une_recherche_coupee_ne_consomme_pas_le_plafond(app, sans_cle) -> None:
    """Sinon une clé oubliée coûterait la journée sans rien avoir cherché."""
    avant = app.offres_etat()["restants"]
    for _ in range(3):
        with pytest.raises(SageError):
            app.offres({})
    assert app.offres_etat()["restants"] == avant


# --- ce qu'il ne fera jamais --------------------------------------------------

def test_chercher_n_ecrit_rien_dans_le_journal(app, client) -> None:
    """« L'autorité reste moi, toujours, avant toute action. »

    Il lit, il écarte, il propose. Une décision naît d'un appui sur `+`, jamais
    d'une liste d'offres — même excellente, même pendant que je dors.
    """
    avant = [(e.entry_id, e.status) for e in app.journal.entries()]
    empreinte = app.journal.review()["chain_intact"]

    app.offres({"precision": "plutôt du tertiaire"})

    assert [(e.entry_id, e.status) for e in app.journal.entries()] == avant
    assert app.journal.review()["chain_intact"] is empreinte is True
    assert not app.journal.entries(status=Status.HAPPENED)


def test_ce_qui_part_est_ce_qu_il_a_dit_de_lui(app, client) -> None:
    """La précision s'ajoute au profil ; elle ne le remplace pas."""
    app.offres({"precision": "pas d'industrie"})
    envoye = client.appels[0]["messages"][0]["content"]

    assert "Toulouse" in envoye
    assert "pas d'industrie" in envoye
    # Les deux genres d'offre, sans hierarchie : il l'a tranche lui-meme le
    # 9 septembre. Le profil disait « poste vise », qui rangeait l'alternance
    # en second ; avant ca il disait « il ne cherche pas d'alternance », ce
    # qu'il n'avait jamais dit.
    assert "alternance" in envoye
    assert "sans preference" in envoye
    assert "poste vise" not in envoye.lower(), "l'un ne passe plus devant l'autre"


# --- les refus, avant la dépense ---------------------------------------------

def test_une_precision_demesuree_est_refusee(app, client) -> None:
    from singular.sage.server import QUESTION_MAX

    with pytest.raises(SageError) as refus:
        app.offres({"precision": "a" * (QUESTION_MAX + 1)})
    assert refus.value.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert client.appels == [], "la précision démesurée est quand même partie"


def test_une_precision_qui_n_est_pas_du_texte_est_refusee(app, client) -> None:
    with pytest.raises(SageError) as refus:
        app.offres({"precision": {"ruse": True}})
    assert refus.value.status == HTTPStatus.BAD_REQUEST
    assert client.appels == []


def test_une_recherche_a_la_fois(app, client) -> None:
    app._un_tour.acquire()
    try:
        with pytest.raises(SageError) as refus:
            app.offres({})
        assert refus.value.status == HTTPStatus.CONFLICT
    finally:
        app._un_tour.release()
    assert client.appels == []


def test_le_verrou_est_partage_avec_la_conversation(app, client) -> None:
    """Même porte-monnaie : deux dépenses simultanées sur un crédit vérifié une fois.

    Deux verrous distincts laisseraient passer une recherche et une réponse en
    même temps, chacune ayant lu le même solde. C'est la course qui vide les
    cinq dollars sans que rien ne l'ait refusée.
    """
    app._un_tour.acquire()
    try:
        for appel in (lambda: app.offres({}), lambda: app.parle({"question": "et alors ?"})):
            with pytest.raises(SageError) as refus:
                appel()
            assert refus.value.status == HTTPStatus.CONFLICT
    finally:
        app._un_tour.release()


def test_le_verrou_est_rendu_meme_quand_la_recherche_refuse(app, sans_cle) -> None:
    with pytest.raises(SageError):
        app.offres({})
    assert app._un_tour.acquire(blocking=False), "le verrou n'a pas été rendu"
    app._un_tour.release()


# --- ce que ça coûte ----------------------------------------------------------

def test_une_recherche_rend_les_offres_et_ce_qu_elle_a_coute(app, client) -> None:
    """Ce qui n'est pas compté ne se voit pas, et le budget est de cinq dollars."""
    plafond = app.offres_etat()["plafond"]
    rendu = app.offres({})

    assert "Chargé d'études CVC" in rendu["offres"]
    assert rendu["cout"]["entree"] == 9000
    assert rendu["cout"]["sortie"] == 1200
    assert rendu["restants"] == plafond - 1


def test_la_depense_survit_au_redemarrage(app, client, tmp_path, monkeypatch) -> None:
    """Le compteur est sur le disque : relancer le serveur ne remet pas à zéro."""
    app.offres({})
    autre = SageApp(DecisionJournal(tmp_path / "journal.db"), token="jeton")
    assert autre.offres_etat()["restants"] == app.offres_etat()["plafond"] - 1


def test_le_plafond_refuse_la_recherche_suivante(app, client, monkeypatch) -> None:
    from singular import parle

    monkeypatch.setattr(parle, "PLAFOND_PAR_JOUR", 2)

    app.offres({})
    app.offres({})
    with pytest.raises(SageError) as refus:
        app.offres({})
    assert refus.value.status == HTTPStatus.TOO_MANY_REQUESTS
    assert len(client.appels) == 2, "la troisième recherche a quand même été facturée"


def test_un_credit_epuise_refuse_avant_de_chercher(app, client, monkeypatch, tmp_path) -> None:
    """Le plafond du jour borne l'emballement ; le crédit est ce qui s'épuise.

    Ses chiffres, pas les miens : le dépôt ne connaît aucun prix, et celui-ci
    vient du fichier de tarifs qu'il remplit lui-même.
    """
    import json

    from singular import parle

    tarifs = tmp_path / "tarifs.json"
    tarifs.write_text(json.dumps({
        "credit_usd": 0.0,
        "modeles": {"claude-opus-5": {"entree": 15.0, "sortie": 75.0,
                                      "cache_lu": 1.5, "cache_ecrit": 18.75}},
    }), encoding="utf-8")
    monkeypatch.setattr(parle, "FICHIER_TARIFS", tarifs)

    with pytest.raises(SageError) as refus:
        app.offres({})
    assert refus.value.status == HTTPStatus.PAYMENT_REQUIRED
    assert client.appels == [], "la recherche est partie malgré un crédit épuisé"
