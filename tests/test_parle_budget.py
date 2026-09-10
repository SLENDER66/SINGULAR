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
import unicodedata

import pytest

from singular.parle import (
    PlafondAtteint,
    Quota,
    Tarifs,
    bilan,
    modele_de_tarifs,
    modeles_qui_depensent,
    phrase_de_bilan,
)

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "singular" / "parle.py"

#: Les nombres a virgule de `parle.py` qui ne sont pas des tarifs, et ce qu'ils
#: mesurent. Tout autre flottant non nul est refuse : un prix code en dur
#: vieillirait en silence et servirait a decider quand s'arreter.
PAS_UN_PRIX = {
    "VERROU_PERIME": "secondes avant de reprendre un verrou abandonne",
    "VERROU_ATTENTE": "secondes entre deux tentatives de prise du verrou",
}

def _sans_accents(texte: str) -> str:
    """La phrase telle qu'on la reconnait, pas telle qu'elle s'ecrit.

    Ces tests attendaient « ecris tes tarifs » et « jetons envoyes » au
    caractere pres. Le jour ou ces mots ont pris leurs accents -- ils sont
    affiches, et le reste de l'ecran est en francais correct -- deux tests sont
    tombes sans qu'aucun comportement ait change. Un test qui punit la
    correction d'un message apprend a ne plus corriger les messages.
    """
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


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
    s'arreter. `modele_de_tarifs()` est le gabarit qu'il remplit : ses valeurs
    sont a zero, donc elles ne peuvent pas se faire passer pour un prix.
    """
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))

    # Les flottants poses sur un nom declare ci-dessus ne sont pas des prix.
    # Sans cette liste, la garde tombait sur la premiere duree venue -- elle
    # refusait « 5.0 secondes » comme un tarif -- et une garde qui crie au loup
    # finit desactivee. La declarer oblige a dire ce que le nombre mesure.
    autorises = set()
    for noeud in ast.walk(arbre):
        cibles = []
        if isinstance(noeud, ast.Assign):
            cibles = [c.id for c in noeud.targets if isinstance(c, ast.Name)]
        elif isinstance(noeud, ast.AnnAssign) and isinstance(noeud.target, ast.Name):
            cibles = [noeud.target.id]
        if any(nom in PAS_UN_PRIX for nom in cibles) and noeud.value is not None:
            autorises.update(id(petit) for petit in ast.walk(noeud.value)
                             if isinstance(petit, ast.Constant))

    suspects = []
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.Constant) and isinstance(noeud.value, float)
                and noeud.value != 0.0 and id(noeud) not in autorises):
            suspects.append(f"ligne {noeud.lineno} : {noeud.value}")
    assert not suspects, (
        "un nombre a virgule dans parle.py ressemble a un tarif code en dur :\n  "
        + "\n  ".join(suspects)
        + "\n\nSi ce n'est pas un prix, pose-le sur un nom et declare-le dans "
          "PAS_UN_PRIX, en disant ce qu'il mesure.")


def test_the_declared_exceptions_still_exist() -> None:
    """Le temoin : une exemption pour un nom disparu affaiblirait la garde en silence."""
    source = SOURCE.read_text(encoding="utf-8")
    for nom in PAS_UN_PRIX:
        assert f"\n{nom} = " in source, f"{nom} n'existe plus dans parle.py"

    gabarit = json.loads(modele_de_tarifs())
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
    gabarit = json.loads(modele_de_tarifs())
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


# --- deux surfaces, un seul fichier -------------------------------------------

def test_le_clavier_ne_mange_pas_le_plafond_du_telephone(tmp_path) -> None:
    """Le défaut que ça corrige : `consommer` incrémentait le compteur du jour
    depuis la ligne de commande, qui écrit le même fichier. Trois questions au
    PC et le téléphone n'en avait plus que cinquante-sept — alors que la
    documentation promet au clavier de ne pas être plafonné.
    """
    chemin = tmp_path / "q.json"
    clavier = Quota(chemin, plafond=60)
    for _ in range(3):
        clavier.ajouter_depense(cout=COUT, modele="m")

    telephone = Quota(chemin, plafond=60)
    assert telephone.restants() == 60, "le clavier a entamé le plafond du téléphone"
    assert telephone.depenses()["m"]["entree"] == 3000, "la dépense n'a pas été comptée"


def test_le_telephone_compte_les_deux(tmp_path) -> None:
    quota = Quota(tmp_path / "q.json", plafond=60)
    quota.consommer(cout=COUT, modele="m")
    assert quota.restants() == 59
    assert quota.depenses()["m"]["entree"] == 1000


def test_la_depense_du_clavier_s_ajoute_a_celle_du_telephone(tmp_path) -> None:
    """Le crédit acheté ne sait pas d'où vient la question."""
    chemin = tmp_path / "q.json"
    Quota(chemin, plafond=60).consommer(cout=COUT, modele="m")
    Quota(chemin, plafond=60).ajouter_depense(cout=COUT, modele="m")

    total = Quota(chemin, plafond=60)
    assert total.depenses()["m"]["entree"] == 2000
    assert total.restants() == 59, "le clavier a bougé le compteur du jour"


def test_une_depense_du_clavier_ne_perd_pas_le_compteur_du_jour(tmp_path) -> None:
    """Elle réécrit le fichier : elle doit préserver ce qu'elle ne touche pas."""
    chemin = tmp_path / "q.json"
    quota = Quota(chemin, plafond=60)
    quota.consommer(cout=COUT, modele="m", aujourdhui="2026-09-07")
    quota.ajouter_depense(cout=COUT, modele="m")

    assert quota.restants(aujourdhui="2026-09-07") == 59


# --- le budget ne doit pas s'aveugler quand on se sert de l'outil -------------

def _tarifs(tmp_path, *, credit=5.0, modeles=("claude-sonnet-5",)):
    chemin = tmp_path / "tarifs.json"
    chemin.write_text(json.dumps({
        "credit_usd": credit,
        "modeles": {nom: {"entree": 3.0, "sortie": 15.0, "cache_lu": 0.3,
                          "cache_ecrit": 3.75} for nom in modeles},
    }), encoding="utf-8")
    return Tarifs(chemin)


def test_the_template_names_every_model_the_tool_can_bill(tmp_path) -> None:
    """Le gabarit ne nommait que le modele de la conversation.

    La recherche d'offres et l'analyse depensent sur un autre. Une seule
    recherche mettait donc dans le compte un modele sans tarif, et `cout_usd`
    rend `None` des qu'il en manque un : l'affichage en dollars disparaissait
    pour de bon, remplace par « ecris tes tarifs » -- ce qu'il avait deja fait.

    Le gabarit est desormais genere depuis les modeles reels. Ce test est ce
    qui empeche une quatrieme faculte de depenser ailleurs sans que personne
    le remarque.
    """
    gabarit = json.loads(modele_de_tarifs())
    assert set(gabarit["modeles"]) == set(modeles_qui_depensent())
    assert len(gabarit["modeles"]) >= 2, "au moins la conversation et la recherche"
    for prix in gabarit["modeles"].values():
        assert set(prix) == set(Tarifs.POSTES)
        assert all(valeur == 0.0 for valeur in prix.values()), (
            "le gabarit ne doit porter aucun prix : ce sont les siens qui comptent")


def test_a_model_without_a_price_does_not_blind_the_whole_ledger(tmp_path) -> None:
    """Le total exact se tait ; le plancher, lui, continue de compter."""
    quota = Quota(tmp_path / "q.json", plafond=50)
    quota.ajouter_depense(cout={"entree": 1_000_000, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-sonnet-5")
    tarifs = _tarifs(tmp_path)
    depenses = quota.depenses()

    assert tarifs.cout_usd(depenses) == pytest.approx(3.0)
    assert tarifs.restant_usd(depenses) == pytest.approx(2.0)

    quota.ajouter_depense(cout={"entree": 1_000_000, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-inconnu")
    depenses = quota.depenses()

    assert tarifs.sans_tarif(depenses) == ["claude-inconnu"]
    assert tarifs.cout_usd(depenses) is None, "un total partiel presente comme un total est faux"
    assert tarifs.restant_usd(depenses) is None
    # Mais la garde, elle, sait encore quelque chose.
    assert tarifs.cout_connu_usd(depenses) == pytest.approx(3.0)
    assert tarifs.restant_au_mieux_usd(depenses) == pytest.approx(2.0)


def test_the_guard_still_refuses_when_the_credit_is_gone(tmp_path) -> None:
    """Une garde qui s'eteint quand on s'en sert est pire que pas de garde.

    C'est ce qui se passait : `restant_usd` vaut `None` des qu'un modele n'a pas
    de tarif, et la route qui refuse une depense sur credit epuise ne se
    declenchait plus du tout. Une seule recherche la desarmait, en silence,
    alors qu'elle protege son argent reel.
    """
    quota = Quota(tmp_path / "q.json", plafond=50)
    quota.ajouter_depense(cout={"entree": 2_000_000, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-sonnet-5")
    quota.ajouter_depense(cout={"entree": 500_000, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-inconnu")
    tarifs = _tarifs(tmp_path, credit=5.0)
    depenses = quota.depenses()

    assert tarifs.restant_usd(depenses) is None, "le total exact reste inconnu"
    # 2 M de jetons d'entree a 3 $/M = 6 $, sur 5 $ de credit : fini.
    assert tarifs.restant_au_mieux_usd(depenses) == 0.0
    assert tarifs.restant_au_mieux_usd(depenses) <= 0, "la route doit refuser"


def test_the_best_case_never_understates_what_is_left(tmp_path) -> None:
    """Refuser dessus arrive tard, jamais trop tot.

    Le plancher ignore ce qu'on ne sait pas chiffrer, donc il surestime ce qui
    reste. C'est ce qui rend le refus sain : si meme en oubliant une depense le
    credit est fini, il est fini.
    """
    quota = Quota(tmp_path / "q.json", plafond=50)
    quota.ajouter_depense(cout={"entree": 100_000, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-sonnet-5")
    tarifs = _tarifs(tmp_path)
    complet = quota.depenses()
    assert tarifs.restant_au_mieux_usd(complet) == tarifs.restant_usd(complet)

    quota.ajouter_depense(cout={"entree": 100_000, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-inconnu")
    partiel = quota.depenses()
    assert tarifs.restant_au_mieux_usd(partiel) >= tarifs.restant_au_mieux_usd(complet) - 1e-9


def test_the_sentence_names_what_is_missing_instead_of_what_he_already_did(tmp_path) -> None:
    """« Ecris tes tarifs » l'envoyait refaire ce qu'il avait deja fait."""
    quota = Quota(tmp_path / "q.json", plafond=50)
    quota.ajouter_depense(cout={"entree": 1000, "sortie": 100, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-inconnu")
    phrase = phrase_de_bilan(bilan(quota, _tarifs(tmp_path)))

    assert "claude-inconnu" in phrase
    assert "ecris tes tarifs" not in _sans_accents(phrase)
    assert "il te reste au plus" in phrase.lower()


def test_without_any_tariff_the_sentence_still_says_where_to_write_them(tmp_path) -> None:
    """Le temoin : quand il n'a rien ecrit, la phrase d'origine reste la bonne."""
    quota = Quota(tmp_path / "q.json", plafond=50)
    quota.ajouter_depense(cout=COUT, modele="claude-sonnet-5")
    phrase = phrase_de_bilan(bilan(quota, Tarifs(tmp_path / "absent.json")))

    assert "ecris tes tarifs" in _sans_accents(phrase)
    assert "jetons envoyes" in _sans_accents(phrase)


def test_every_faculty_that_spends_writes_it_down(tmp_path, monkeypatch, capsys) -> None:
    """Trois facultes depensent ; une seule ne comptait rien.

    `python -m singular analyse` appelait un modele et n'enregistrait pas un
    jeton : le solde affiche sur le telephone etait faux de tout ce qui avait
    ete analyse au clavier. Meme cause que pour la recherche d'offres la veille
    -- la fonction ne rendait pas son cout, donc l'appelant ne pouvait pas
    l'ecrire.

    Ce test passe par la ligne de commande, pas par la fonction : c'est le
    branchement qui manquait, et une fonction juste avec un appelant muet fait
    exactement le meme degat.
    """
    from singular import parle
    from singular.__main__ import main
    from singular.journal import DecisionJournal, Tier

    monkeypatch.setattr(parle, "FICHIER_QUOTA", tmp_path / "quota.json")
    monkeypatch.setattr(parle, "FICHIER_TARIFS", tmp_path / "absent.json")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-pour-le-test")

    db = str(tmp_path / "journal.db")
    DecisionJournal(db).add(title="t", action="a", predicted="p", probability=0.6,
                            tier=Tier.REVENUS, cost_hours=1, horizon_days=7)

    class FauxBloc:
        type = "text"
        text = "Trois phrases."

    class FausseConso:
        input_tokens, output_tokens = 4321, 765
        cache_read_input_tokens = cache_creation_input_tokens = 0

    class FausseReponse:
        content, stop_reason, usage = [FauxBloc()], "end_turn", FausseConso()

    class FauxClient:
        @property
        def beta(self): return self
        @property
        def messages(self): return self
        def create(self, **_): return FausseReponse()

    from singular import analyse
    vrai = analyse.analyser
    monkeypatch.setattr(analyse, "analyser",
                        lambda notice, *, modele=None, client=None:
                        vrai(notice, modele=modele, client=client or FauxClient()))

    assert Quota().depenses() == {}
    assert main(["--db", db, "analyse"]) == 0

    depenses = Quota().depenses()
    assert depenses, "l'analyse a depense sans que rien ne l'enregistre"
    total = sum(compte["entree"] for compte in depenses.values())
    assert total == 4321
    assert "4321 jetons envoyes" in capsys.readouterr().out


# --- deux ecrivains sur le meme fichier ---------------------------------------

def test_two_writers_at_once_lose_nothing(tmp_path) -> None:
    """Le serveur du Sage et le clavier ecrivent le meme fichier.

    Une reponse depuis le telephone pendant un `python -m singular parle` au
    clavier, et les deux lisaient le meme total avant d'ecrire chacun le sien.
    Mesure avant correction, huit processus et quarante depenses : neuf
    plantages -- le fichier provisoire portait un nom fixe, le second ecrivain
    ne le retrouvait plus -- et vingt et une depenses perdues.

    Ce que ca coutait : le compte sous-estime la depense, donc la garde qui
    refuse sur credit epuise refuse trop tard. C'est la faute deja payee sur le
    journal, deux verdicts simultanes acceptes, transposee a son argent.

    Des fils et une barriere plutot que des processus : un test doit tomber
    quand on retire ce qu'il tient, et des processus lances par `spawn` mettent
    si longtemps a demarrer qu'ils ne se rencontrent jamais -- la premiere
    version de ce test passait sans le verrou, donc ne prouvait rien. La
    barriere force la rencontre. Ce qu'elle ne prouve pas : que le verrou tient
    entre deux processus. C'est pour ca que c'est un fichier verrou et pas un
    verrou memoire, et le serveur du Sage est de toute facon multi-fils.
    """
    import threading

    chemin = tmp_path / "quota.json"
    ecrivains = 12
    depart = threading.Barrier(ecrivains)
    incidents: list[str] = []

    def depenser() -> None:
        quota = Quota(chemin, plafond=10_000)
        depart.wait()
        try:
            quota.ajouter_depense(cout={"entree": 1, "sortie": 0, "cache_lu": 0,
                                        "cache_ecrit": 0}, modele="claude-sonnet-5")
        except Exception as erreur:  # noqa: BLE001 - c'est ce qu'on mesure
            incidents.append(type(erreur).__name__)

    fils = [threading.Thread(target=depenser) for _ in range(ecrivains)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=30)

    assert incidents == [], f"des depenses ont plante : {sorted(set(incidents))}"
    ecrites = json.loads(chemin.read_text(encoding="utf-8"))["jetons"]
    assert ecrites["claude-sonnet-5"]["entree"] == ecrivains, (
        "des depenses simultanees se sont ecrasees : le compte sous-estime, "
        "donc la garde du credit refuse trop tard")


def test_the_daily_cap_is_not_overrun_by_simultaneous_turns(tmp_path) -> None:
    """Le plafond se lit puis s'ecrit : sans verrou, tout le monde lit le meme.

    Le degat n'est pas le meme que pour la depense -- ici c'est le plafond qui
    saute, et il existe pour proteger d'une soiree distraite.
    """
    import threading

    chemin = tmp_path / "quota.json"
    plafond, ecrivains = 4, 12
    depart = threading.Barrier(ecrivains)
    acceptes: list[int] = []

    def un_tour() -> None:
        quota = Quota(chemin, plafond=plafond)
        depart.wait()
        try:
            acceptes.append(quota.consommer(cout=COUT, modele="claude-sonnet-5"))
        except PlafondAtteint:
            pass

    fils = [threading.Thread(target=un_tour) for _ in range(ecrivains)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=30)

    assert len(acceptes) == plafond, f"{len(acceptes)} tours acceptes pour un plafond de {plafond}"
    assert sorted(acceptes) == list(range(plafond)), "deux tours ont recu le meme reste"


def test_an_abandoned_lock_does_not_freeze_the_tool(tmp_path, monkeypatch) -> None:
    """Un processus tue en tenant le verrou condamnerait l'outil pour toujours."""
    from singular import parle

    chemin = tmp_path / "quota.json"
    quota = Quota(chemin, plafond=10)
    verrou = chemin.with_suffix(".verrou")
    verrou.parent.mkdir(parents=True, exist_ok=True)
    verrou.write_text("", encoding="utf-8")

    monkeypatch.setattr(parle, "VERROU_PERIME", 0.0)  # il est deja perime
    quota.ajouter_depense(cout={"entree": 7, "sortie": 0, "cache_lu": 0,
                                "cache_ecrit": 0}, modele="claude-sonnet-5")

    assert quota.depenses()["claude-sonnet-5"]["entree"] == 7
    assert not verrou.exists(), "le verrou doit etre rendu"
