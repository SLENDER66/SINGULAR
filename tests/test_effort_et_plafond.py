"""Deux reglages qui avaient l'air independants, et une reponse coupee.

`max_tokens` plafonne tout ce que le modele produit : sa reflexion d'abord, sa
reponse ensuite. `SINGULAR_ANALYSE_EFFORT` achete de la reflexion. Les deux
existaient deja, la variable acceptait deja « xhigh », et le plafond restait a
2000 : de quoi recevoir un commentaire coupe au milieu d'une phrase -- rendu
sans un mot, parce que seul le refus du modele etait verifie.

Ce fichier tient les trois moities de la correction : le plafond suit l'effort,
une reponse coupee est refusee au lieu d'etre rendue, et l'appel qui a echoue
apres avoir ete facture est quand meme compte.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest

import singular.analyse as analyse
import singular.offres as offres
import singular.parle as parle
from singular.analyse import (
    EFFORTS,
    MARGE_DE_REFLEXION,
    AnalyseIndisponible,
    jetons_max,
)
from singular.parle import Conversation, Quota


class FauxBloc:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FausseConso:
    input_tokens = 900
    output_tokens = 2000
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class FausseReponse:
    def __init__(self, texte: str = "Une phrase qui s'arrete au milieu du",
                 stop_reason: str = "max_tokens") -> None:
        self.content = [FauxBloc(texte)]
        self.stop_reason = stop_reason
        self.usage = FausseConso()


class FauxClient:
    def __init__(self, reponse: FausseReponse | None = None) -> None:
        self.appels: list[dict[str, Any]] = []
        self._reponse = reponse or FausseReponse()

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return self._reponse


# --- le plafond suit l'effort -------------------------------------------------

def test_le_plafond_monte_avec_l_effort() -> None:
    """Un effort plus haut reflechit plus longtemps : il lui faut la place."""
    assert jetons_max(2000, "medium") == 2000
    assert jetons_max(2000, "high") > jetons_max(2000, "medium")
    assert jetons_max(2000, "xhigh") > jetons_max(2000, "high")
    assert jetons_max(2000, "max") > jetons_max(2000, "xhigh")


def test_chaque_effort_acceptable_a_sa_marge() -> None:
    """La garde qui rend la panne impossible plutot que corrigee.

    `effort_valide` ne rend que des valeurs de `EFFORTS`. Ajouter un niveau la
    sans lui donner de marge ici, c'est reintroduire exactement la troncature
    qu'on vient de corriger -- et elle ne se verrait qu'un soir, sur une
    reponse coupee. Ce test echoue a la place du prochain lecteur.
    """
    assert set(MARGE_DE_REFLEXION) == set(EFFORTS)
    for effort in EFFORTS:
        assert jetons_max(1000, effort) >= 1000


def test_un_effort_inconnu_est_refuse() -> None:
    """Un repli silencieux sur la marge la plus basse recreerait la panne."""
    with pytest.raises(ValueError):
        jetons_max(2000, "ultra")


def test_un_budget_de_reponse_nul_est_refuse() -> None:
    with pytest.raises(ValueError):
        jetons_max(0, "medium")


def test_les_trois_facultes_reservent_la_place_de_la_reflexion() -> None:
    """Ce qui part vraiment au service, pour les trois qui depensent."""
    for module in (analyse, parle, offres):
        assert module.JETONS_MAX == jetons_max(module.JETONS_REPONSE, module.EFFORT)
        assert module.JETONS_MAX >= module.JETONS_REPONSE


def test_le_plafond_envoye_est_bien_celui_du_module() -> None:
    client = FauxClient(FausseReponse("Rien d'inquietant.", stop_reason="end_turn"))
    analyse.analyser({"headline": "x", "items": []}, client=client)
    assert client.appels[0]["max_tokens"] == analyse.JETONS_MAX


# --- une reponse coupee n'est pas une reponse ---------------------------------

def test_l_analyse_refuse_une_reponse_coupee() -> None:
    """Sa derniere phrase peut dire le contraire de celle qu'elle n'a pas ecrite."""
    client = FauxClient(FausseReponse())
    with pytest.raises(AnalyseIndisponible):
        analyse.analyser({"headline": "x", "items": []}, client=client)


def test_les_offres_refusent_une_reponse_coupee() -> None:
    client = FauxClient(FausseReponse())
    with pytest.raises(AnalyseIndisponible):
        offres.chercher("developpeur", client=client)


def test_un_tour_coupe_n_entre_pas_dans_le_fil(tmp_path) -> None:
    """Le fil est renvoye en entier a chaque tour : une phrase coupee dedans
    contaminerait toutes les reponses suivantes, pas seulement celle-la."""
    fil = Conversation(tmp_path / "conversation.json")
    client = FauxClient(FausseReponse())
    with pytest.raises(AnalyseIndisponible):
        parle.repondre("et maintenant ?", "contexte", fil, client=client)
    assert fil.tours == []


# --- ce qui a ete paye est compte ---------------------------------------------

def test_l_exception_porte_ce_que_l_appel_a_coute() -> None:
    """Les jetons sont partis : le compteur doit les voir passer."""
    for stop in ("max_tokens", "refusal"):
        client = FauxClient(FausseReponse("", stop_reason=stop))
        with pytest.raises(AnalyseIndisponible) as leve:
            analyse.analyser({"headline": "x", "items": []}, client=client)
        assert leve.value.cout is not None
        assert leve.value.cout["sortie"] == FausseConso.output_tokens


def test_une_panne_avant_l_appel_ne_coute_rien() -> None:
    """Pas de cle, pas de reseau : rien n'est parti, il n'y a rien a compter."""
    assert AnalyseIndisponible(analyse.REFUS["sans_cle"]).cout is None


def test_le_serveur_compte_un_appel_paye_qui_a_echoue(tmp_path) -> None:
    from singular.sage.server import _compter_l_appel_paye

    quota = Quota(tmp_path / "q.json", plafond=10)
    exc = AnalyseIndisponible("coupee", cout={"entree": 900, "sortie": 2000,
                                              "cache_lu": 0, "cache_ecrit": 0})
    _compter_l_appel_paye(exc, quota, "claude-sonnet-5")
    assert quota.depenses()["claude-sonnet-5"]["sortie"] == 2000


def test_le_serveur_ne_compte_rien_quand_rien_n_est_parti(tmp_path) -> None:
    from singular.sage.server import _compter_l_appel_paye

    quota = Quota(tmp_path / "q.json", plafond=10)
    _compter_l_appel_paye(AnalyseIndisponible("pas de cle"), quota, "claude-sonnet-5")
    assert quota.depenses() == {}


def test_le_clavier_compte_un_appel_paye_qui_a_echoue(tmp_path, monkeypatch) -> None:
    from singular.__main__ import _compter_l_appel_paye

    monkeypatch.setattr(parle, "FICHIER_QUOTA", tmp_path / "q.json")
    exc = AnalyseIndisponible("coupee", cout={"entree": 900, "sortie": 2000,
                                              "cache_lu": 0, "cache_ecrit": 0})
    _compter_l_appel_paye(exc, "claude-sonnet-5")
    assert Quota(tmp_path / "q.json").depenses()["claude-sonnet-5"]["sortie"] == 2000


# --- et la doc qui le dit ------------------------------------------------------

RACINE = pathlib.Path(__file__).resolve().parent.parent


def test_usage_nomme_exactement_les_efforts_acceptes() -> None:
    """La doc listait trois niveaux quand le code en acceptait cinq.

    Ce n'etait pas un detail de redaction : les deux niveaux non documentes sont
    precisement ceux qui coutent le plus et qui, avec l'ancien plafond, rendaient
    une reponse coupee. Une liste ecrite a la main derive ; celle-ci est tenue
    par la seule qui fasse foi, `EFFORTS`.
    """
    texte = (RACINE / "USAGE.md").read_text(encoding="utf-8")
    paragraphes = [bloc for bloc in texte.split("\n\n") if "SINGULAR_ANALYSE_EFFORT" in bloc]
    assert len(paragraphes) == 1, (
        "un seul paragraphe de USAGE.md doit expliquer SINGULAR_ANALYSE_EFFORT : "
        f"il y en a {len(paragraphes)}"
    )
    cites = {mot for mot in re.findall(r"`([^`]+)`", paragraphes[0])
             if not mot.startswith("SINGULAR_")}
    assert cites == set(EFFORTS), (
        "USAGE.md ne nomme pas les memes efforts que le code : "
        f"doc {sorted(cites)}, code {sorted(EFFORTS)}"
    )
