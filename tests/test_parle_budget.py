"""Ce que la conversation coute, et pourquoi ce depot n'ecrit aucun prix.

Cinq dollars de credit achetes. La question qui compte n'est plus « combien de
jetons » mais « est-ce que je suis en train de les bruler ». Ce fichier tient
les deux moities de la reponse : le compteur, qui ne se remet jamais a zero, et
les tarifs, qui viennent de lui et jamais d'ici.

La regle qui traverse tout : aucun prix n'est ecrit dans ce depot. Les tarifs
changent, ce depot ne se met pas a jour tout seul, et un chiffre faux servirait
a decider quand s'arreter. Un test le verifie sur le source.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from singular.parle import (
    MODELE_DE_TARIFS,
    PlafondAtteint,
    Quota,
    Tarifs,
    bilan,
    phrase_de_bilan,
)

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "singular" / "parle.py"

COUT = {"entree": 1000, "sortie": 200, "cache_lu": 5000, "cache_ecrit": 0}


# --- le compteur --------------------------------------------------------------

def test_la_depense_s_accumule_modele_par_modele(tmp_path) -> None:
    """Un total unique melangerait des jetons qui ne coutent pas le meme prix."""
    quota = Quota(tmp_path / "q.json", plafond=10)
    quota.consommer(cout=COUT, modele="claude-sonnet-5")
    quota.consommer(cout=COUT, modele="claude-opus-5")
    quota.consommer(cout=COUT, modele="claude-sonnet-5")

    depenses = quota.depenses()
    assert set(depenses) == {"claude-sonnet-5", "claude-opus-5"}
    assert depenses["claude-sonnet-5"]["entree"] == 2000
    assert depenses["claude-opus-5"]["entree"] == 1000


def test_la_depense_survit_au_redemarrage(tmp_path) -> None:
    """Sinon le total afficherait la soiree, pas le credit."""
    Quota(tmp_path / "q.json", plafond=10).consommer(cout=COUT, modele="m")
    assert Quota(tmp_path / "q.json").depenses()["m"]["sortie"] == 200


def test_la_depense_ne_repart_pas_le_lendemain(tmp_path) -> None:
    """Le plafond est quotidien ; le credit achete, non."""
    quota = Quota(tmp_path / "q.json", plafond=10)
    quota.consommer(cout=COUT, modele="m", aujourdhui="2026-09-07")
    quota.consommer(cout=COUT, modele="m", aujourdhui="2026-09-08")

    assert quota.restants(aujourdhui="2026-09-08") == 9, "le plafond n'a pas repris"
    assert quota.depenses()["m"]["entree"] == 2000, "le total a ete efface"


def test_un_tour_refuse_ne_compte_aucune_depense(tmp_path) -> None:
    quota = Quota(tmp_path / "q.json", plafond=1)
    quota.consommer(cout=COUT, modele="m")
    with pytest.raises(PlafondAtteint):
        quota.consommer(cout=COUT, modele="m")
    assert quota.depenses()["m"]["entree"] == 1000


def test_un_tour_sans_cout_compte_quand_meme(tmp_path) -> None:
    """L'ancien appel, sans facture : il doit rester valide."""
    quota = Quota(tmp_path / "q.json", plafond=5)
    assert quota.consommer() == 4
    assert quota.depenses() == {}


def test_un_compteur_d_une_ancienne_version_est_relu(tmp_path) -> None:
    """Le fichier existait avant que la depense y entre. Le relire ne doit ni
    echouer, ni perdre le compte du jour."""
    chemin = tmp_path / "q.json"
    chemin.write_text(json.dumps({"jour": "2026-09-07", "tours": 3}), encoding="utf-8")
    quota = Quota(chemin, plafond=20)

    assert quota.restants(aujourdhui="2026-09-07") == 17
    assert quota.depenses() == {}
    quota.consommer(cout=COUT, modele="m", aujourdhui="2026-09-07")
    assert quota.restants(aujourdhui="2026-09-07") == 16


def test_un_compteur_absurde_ne_fait_pas_tomber_la_lecture(tmp_path) -> None:
    chemin = tmp_path / "q.json"
    chemin.write_text(json.dumps({"jour": "2026-09-07", "tours": "beaucoup",
                                  "jetons": "pas un dictionnaire"}), encoding="utf-8")
    quota = Quota(chemin, plafond=20)
    assert quota.restants(aujourdhui="2026-09-07") == 20
    assert quota.depenses() == {}


# --- les tarifs, qui sont les siens -------------------------------------------

def test_aucun_prix_n_est_ecrit_dans_le_depot() -> None:
    """La regle, verifiee sur le source plutot que promise.

    Un tarif code en dur vieillirait en silence et servirait a decider quand
    s'arreter. `MODELE_DE_TARIFS` est le gabarit qu'il remplit : ses valeurs
    sont a zero, donc elles ne peuvent pas se faire passer pour un prix.
    """
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    suspects = []
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Constant) and isinstance(noeud.value, float)
                and noeud.value != 0.0):
            suspects.append(f"ligne {noeud.lineno} : {noeud.value}")
    assert not suspects, (
        "un nombre a virgule dans parle.py ressemble a un tarif code en dur :\n  "
        + "\n  ".join(suspects))

    gabarit = json.loads(MODELE_DE_TARIFS)
    prix = gabarit["modeles"]["claude-sonnet-5"]
    assert set(prix.values()) == {0.0}, "le gabarit propose des prix inventes"


def test_sans_tarifs_aucun_montant_n_est_affiche(tmp_path) -> None:
    """Tant qu'il n'a rien ecrit, la conversation compte des jetons."""
    quota = Quota(tmp_path / "q.json", plafond=10)
    quota.consommer(cout=COUT, modele="claude-sonnet-5")

    compte = bilan(quota, Tarifs(tmp_path / "absent.json"))
    assert compte["usd"] is None
    assert "jetons" in phrase_de_bilan(compte)
    assert "$" not in phrase_de_bilan(compte)


def test_avec_ses_tarifs_le_montant_apparait(tmp_path) -> None:
    (tmp_path / "t.json").write_text(json.dumps({
        "credit_usd": 5.0,
        "modeles": {"m": {"entree": 3.0, "sortie": 15.0, "cache_lu": 0.3, "cache_ecrit": 3.75}},
    }), encoding="utf-8")
    quota = Quota(tmp_path / "q.json", plafond=10)
    quota.consommer(cout={"entree": 1_000_000, "sortie": 0, "cache_lu": 0, "cache_ecrit": 0},
                    modele="m")

    compte = bilan(quota, Tarifs(tmp_path / "t.json"))
    assert compte["usd"] == pytest.approx(3.0)
    assert compte["restant_usd"] == pytest.approx(2.0)
    assert "2.00 $" in phrase_de_bilan(compte)


def test_un_modele_sans_tarif_rend_none_et_pas_un_total_partiel(tmp_path) -> None:
    """Un chiffre qui oublie un modele sert quand meme a decider quand
    s'arreter. C'est pour ca qu'il ne doit pas exister."""
    (tmp_path / "t.json").write_text(json.dumps({
        "credit_usd": 5.0, "modeles": {"connu": {"entree": 3.0}},
    }), encoding="utf-8")
    quota = Quota(tmp_path / "q.json", plafond=10)
    quota.consommer(cout=COUT, modele="connu")
    quota.consommer(cout=COUT, modele="inconnu")

    compte = bilan(quota, Tarifs(tmp_path / "t.json"))
    assert compte["usd"] is None
    assert compte["restant_usd"] is None


def test_le_credit_ne_descend_pas_sous_zero(tmp_path) -> None:
    (tmp_path / "t.json").write_text(json.dumps({
        "credit_usd": 1.0, "modeles": {"m": {"entree": 3.0}},
    }), encoding="utf-8")
    quota = Quota(tmp_path / "q.json", plafond=10)
    quota.consommer(cout={"entree": 1_000_000}, modele="m")

    assert bilan(quota, Tarifs(tmp_path / "t.json"))["restant_usd"] == 0.0


def test_des_tarifs_illisibles_ne_cassent_pas_la_conversation(tmp_path) -> None:
    """Une faute de frappe dans un fichier qu'il edite a la main ne doit pas
    lui couper la parole -- elle doit juste faire disparaitre les dollars."""
    (tmp_path / "t.json").write_text("{ceci n'est pas du json", encoding="utf-8")
    tarifs = Tarifs(tmp_path / "t.json")
    assert tarifs.modeles == {}
    assert tarifs.credit is None


def test_un_tarif_qui_n_est_pas_un_nombre_est_ignore(tmp_path) -> None:
    (tmp_path / "t.json").write_text(json.dumps({
        "credit_usd": "cinq", "modeles": {"m": {"entree": "trois", "sortie": 15.0}},
    }), encoding="utf-8")
    tarifs = Tarifs(tmp_path / "t.json")
    assert tarifs.credit is None
    assert tarifs.modeles == {"m": {"sortie": 15.0}}


def test_le_gabarit_est_du_json_valide() -> None:
    """Il est colle tel quel dans un fichier. S'il ne se relit pas, il ne sert
    a rien -- et l'erreur apparaitrait chez lui, pas ici."""
    gabarit = json.loads(MODELE_DE_TARIFS)
    assert set(gabarit) == {"credit_usd", "modeles"}
    assert set(next(iter(gabarit["modeles"].values()))) == set(Tarifs.POSTES)


def test_sans_aucun_tarif_le_zero_lui_meme_est_tu(tmp_path) -> None:
    """« 0,00 $ dépensés » serait vrai et trompeur : il laisserait croire que
    ce dépôt connaît les prix, alors qu'il attend les siens."""
    vide = Quota(tmp_path / "q.json", plafond=10)
    assert bilan(vide, Tarifs(tmp_path / "absent.json"))["usd"] is None


def test_avec_des_tarifs_et_rien_de_depense_le_zero_est_dit(tmp_path) -> None:
    (tmp_path / "t.json").write_text(json.dumps({
        "credit_usd": 5.0, "modeles": {"m": {"entree": 3.0}},
    }), encoding="utf-8")
    compte = bilan(Quota(tmp_path / "q.json", plafond=10), Tarifs(tmp_path / "t.json"))
    assert compte["usd"] == 0.0
    assert compte["restant_usd"] == 5.0
