"""Le prototype de suivi de candidatures : ses deux promesses affichées.

Ce fichier est explicitement hors de l'architecture de SINGULAR — un
prototype jetable, écrit pour une semaine d'essai. Il n'était couvert par
aucun test, et ça se défendait tant qu'il ne promettait rien.

Il promet maintenant deux choses, à l'écran, à quelqu'un qui les croira :

* « Rien n'est parti d'ici : ce script ne contacte aucun serveur. » Une
  phrase juste peut devenir fausse sans que la ligne qui la contient change
  — c'était déjà la forme du bug `authorised()` du serveur du Sage. Ici
  c'est pire : la phrase est affichée à l'utilisateur comme une garantie.
* le bloc à coller dans l'app Claude doit vraiment porter la situation, sinon
  le pont ne sert à rien : autant retaper à la main, ce qu'il existe pour
  éviter.

`tests/test_windows_console.py` couvre par ailleurs, depuis le même commit,
le fait que sa sortie tienne dans une console Windows.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import sys

import pytest

from tests.support import sans_accents

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "proto" / "suivi_candidatures.py"

#: Tout ce que le prototype a le droit d'importer. La liste est courte
#: exprès : elle est la définition exécutable de « bibliothèque standard
#: seule, aucun réseau ». Un ajout ici est une décision, pas un détail.
IMPORTS_AUTORISES = {"__future__", "json", "sys", "textwrap", "datetime", "pathlib"}


def _charger():
    """Importe le prototype par son chemin : `proto/` n'est pas un paquet."""
    spec = importlib.util.spec_from_file_location("proto_suivi", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["proto_suivi"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def proto(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    module = _charger()
    module.FICHIER = tmp_path / ".singular" / "candidatures.json"
    return module


def test_il_n_importe_rien_qui_puisse_parler_au_reseau() -> None:
    """La garantie affichée à l'utilisateur, vérifiée sur le code réel.

    On juge les imports plutôt que de chercher des noms d'hôtes : c'est la
    seule porte par laquelle une requête pourrait sortir d'un fichier qui
    n'utilise que la bibliothèque standard.
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    importes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            importes.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            importes.add(node.module.split(".")[0])

    interdits = importes - IMPORTS_AUTORISES
    assert not interdits, (
        "le prototype affiche « ce script ne contacte aucun serveur » ; "
        f"ces imports ne sont pas couverts par cette promesse : {sorted(interdits)}"
    )


def test_le_bloc_pour_claude_porte_la_situation(proto) -> None:
    """Le pont doit dire ce que Claude oublie : le profil, l'état, la question."""
    donnees = {
        "candidatures": [
            {"entreprise": "BE Fluides Occitanie", "poste": "Charge d'etudes CVC",
             "statut": "envoyee", "date_ajout": "2026-08-26",
             "date_statut": "2026-08-26", "notes": ["Vu sur Indeed"]},
        ],
        "cv": {"poste": [{"etape": "Changer le titre", "fait": False},
                         {"etape": "Traduire trois chantiers", "fait": True}],
               "alternance": [{"etape": "Assumer l'alternance", "fait": False}]},
    }

    bloc = proto.texte_pour_claude(donnees, "relis le titre de mon CV")

    assert "bts fluides energies domotique" in sans_accents(bloc)   # qui je suis
    assert "BE Fluides Occitanie" in bloc               # ou j'en suis
    assert "Vu sur Indeed" in bloc                      # ce que j'avais note
    assert "Changer le titre" in bloc                   # ce qu'il me reste
    assert "relis le titre de mon CV" in bloc           # ce que je demande
    assert "Traduire trois chantiers" not in bloc, (
        "une etape deja faite encombre le bloc sans rien apprendre"
    )


def test_le_bloc_ne_revele_pas_les_candidatures_classees(proto) -> None:
    """Un refus n'a rien à faire dans une question posée aujourd'hui."""
    donnees = {
        "candidatures": [
            {"entreprise": "Refusee SA", "poste": "Chiffreur", "statut": "refus",
             "date_ajout": "2026-08-01", "date_statut": "2026-08-20", "notes": []},
        ],
        "cv": {"poste": [{"etape": "Changer le titre", "fait": True}],
               "alternance": [{"etape": "Assumer l'alternance", "fait": True}]},
    }

    bloc = proto.texte_pour_claude(donnees, "et maintenant ?")

    assert "Refusee SA" not in bloc
    assert "je n'ai pas encore commence" in sans_accents(bloc)
    assert "mes deux cv sont termines." in sans_accents(bloc)


def test_les_etapes_du_cv_se_mettent_a_jour_tant_que_rien_n_est_coche(proto, tmp_path) -> None:
    """Un fichier déjà créé ne doit pas rester sur une liste d'étapes fausse.

    Les huit étapes ont été écrites en supposant une reconversion depuis le
    terrain, alors que les deux ans de bureau d'études étaient déjà faits.
    Sans ceci, un fichier existant gardait l'ancienne liste pour toujours et
    la seule sortie était d'effacer ses données.
    """
    proto.FICHIER.parent.mkdir(parents=True, exist_ok=True)
    proto.FICHIER.write_text(json.dumps({
        "candidatures": [],
        "cv": [{"etape": "Une etape d'avant", "fait": False}],
    }), encoding="utf-8")

    donnees = proto.charger()

    assert {nom: [e["etape"] for e in etapes] for nom, etapes in donnees["cv"].items()} \
        == proto.TEXTES_CV


def test_une_etape_deja_cochee_interdit_la_mise_a_jour(proto) -> None:
    """Le travail déjà fait vaut mieux qu'une liste à jour : on ne l'efface pas."""
    proto.FICHIER.parent.mkdir(parents=True, exist_ok=True)
    proto.FICHIER.write_text(json.dumps({
        "candidatures": [],
        "cv": [{"etape": "Une etape d'avant", "fait": True},
               {"etape": "Une autre", "fait": False}],
    }), encoding="utf-8")

    donnees = proto.charger()

    assert [e["etape"] for e in donnees["cv"][proto.CV_POSTE]] \
        == ["Une etape d'avant", "Une autre"], "le travail deja fait ne se perd pas"
    assert [e["etape"] for e in donnees["cv"][proto.CV_ALTERNANCE]] \
        == proto.TEXTES_CV[proto.CV_ALTERNANCE], "la seconde liste demarre a zero"
    assert not any(e["fait"] for e in donnees["cv"][proto.CV_ALTERNANCE]), (
        "personne n'a jamais coche une etape de la seconde liste")


# --- rien sur sa vie qui ne vienne de lui ------------------------------------

def test_chaque_ligne_de_profil_porte_sa_provenance(proto) -> None:
    """Deux fois dans la même journée, une session a déduit un fait de sa vie.

    « Il vient du terrain, donc c'est une reconversion » a effacé deux ans de
    bureau d'études. « Chambre froide et brûleur, donc pas de tertiaire » l'a
    écarté du marché toulousain le plus large, alors qu'il fait des CTA double
    flux. Aucune des deux n'a été demandée, et les deux se sont écrites ici
    comme des faits.

    Une consigne — « ne déduis pas » — se lit ou ne se lit pas. Une chaîne nue
    dans PROFIL, elle, échoue.
    """
    fautes = [
        f"« {entree!r} »"
        for entree in proto.PROFIL
        if not (isinstance(entree, tuple) and len(entree) == 2
                and isinstance(entree[0], str) and entree[1] in (proto.DIT, proto.DEDUIT))
    ]

    assert not fautes, (
        "chaque ligne de PROFIL doit dire d'ou elle vient -- DIT ou DEDUIT :\n  "
        + "\n  ".join(fautes)
        + "\n  Une chaine seule voudrait dire « quelqu'un l'a ecrit, on ne sait plus qui »."
    )


def test_chaque_etape_du_cv_porte_sa_provenance(proto) -> None:
    """Le meme marquage, a l'endroit ou la correction s'etait arretee.

    `PROFIL` portait sa provenance ; `ETAPES_CV` non. Or ce sont des conseils
    sur sa vie exactement au meme titre -- ils s'affichent chaque matin comme
    l'action du jour, et ils partent dans le bloc colle a Claude. Une etape
    disait « retirer toute mention d'alternance » alors qu'il venait de
    trancher, en questionnaire, qu'il cherche les deux sans hierarchie.
    """
    fautes = [
        f"« {entree!r} »"
        for etapes in proto.ETAPES_CV.values() for entree in etapes
        if not (isinstance(entree, tuple) and len(entree) == 2
                and isinstance(entree[0], str) and entree[1] in (proto.DIT, proto.DEDUIT))
    ]

    assert not fautes, (
        "chaque etape du CV doit dire d'ou elle vient -- DIT ou DEDUIT :\n  "
        + "\n  ".join(fautes)
        + "\n  Une etape conseille sa vie : elle vaut une ligne de profil."
    )


def test_une_etape_deduite_ne_voyage_pas_deguisee(proto) -> None:
    """Le mecanisme, eprouve meme quand aucune etape reelle n'est deduite.

    Une etape l'a ete : « retirer toute mention d'alternance », que personne ne
    montrait qu'il avait dite. Il a tranche depuis, donc plus rien n'est marque
    -- et un test qui se contenterait de parcourir les etapes reelles ne
    garderait alors plus rien. Celui-ci en injecte une.
    """
    veritables = {nom: list(etapes) for nom, etapes in proto.ETAPES_CV.items()}
    invente = "Ne postuler qu'aux grosses boites"
    try:
        proto.ETAPES_CV[proto.CV_POSTE].append((invente, proto.DEDUIT))
        proto.PROVENANCE_CV[invente] = proto.DEDUIT

        assert "(deduit" in sans_accents(proto.marque(invente))
        donnees = {"candidatures": [],
                   "cv": {nom: [{"etape": invente, "fait": False}]
                          for nom in proto.TEXTES_CV}}
        bloc = proto.texte_pour_claude(donnees, "relis mon CV")
        ligne_deduite = next(texte for texte in bloc.splitlines() if invente in texte)
        assert "(deduit" in sans_accents(ligne_deduite), (
            "l'etape part chez Claude comme un fait acquis : c'est exactement le "
            "mecanisme qui a produit un CV faux")
    finally:
        for nom, etapes in veritables.items():
            proto.ETAPES_CV[nom][:] = etapes
        proto.PROVENANCE_CV.pop(invente, None)


def test_un_fait_dit_ne_porte_aucune_marque(proto) -> None:
    """L'inverse : tout marquer affaiblirait ce que la marque veut dire."""
    for textes in proto.TEXTES_CV.values():
        for texte in textes:
            assert proto.marque(texte) == texte


def test_une_etape_inconnue_ne_se_marque_pas(proto) -> None:
    """Le fichier d'avant ce marquage ne doit pas devenir suspect d'un coup."""
    assert proto.marque("Une etape ecrite avant ce marquage") == "Une etape ecrite avant ce marquage"


def test_une_deduction_est_affichee_comme_non_verifiee(proto) -> None:
    """Si une déduction entre quand même, elle ne doit pas voyager déguisée."""
    donnees = {"candidatures": [], "cv": {"poste": [{"etape": "x", "fait": True}],
                                          "alternance": [{"etape": "y", "fait": True}]}}
    veritable = list(proto.PROFIL)
    try:
        proto.PROFIL.append(("Il vise plutot l'industriel.", proto.DEDUIT))
        bloc = proto.texte_pour_claude(donnees, "une question")
    finally:
        proto.PROFIL[:] = veritable

    assert "ceci n'est pas verifie" in sans_accents(bloc)
    assert "Il vise plutot l'industriel." in bloc
    ligne = next(texte_ligne for texte_ligne in bloc.splitlines() if "industriel" in texte_ligne)
    assert ligne.startswith("- "), "une deduction doit etre listee a part, pas fondue dans le profil"


def test_un_fait_dit_n_est_pas_marque_comme_incertain(proto) -> None:
    """L'inverse : signaler tout affaiblirait ce que le signal veut dire."""
    donnees = {"candidatures": [], "cv": {"poste": [{"etape": "x", "fait": True}],
                                          "alternance": [{"etape": "y", "fait": True}]}}

    bloc = proto.texte_pour_claude(donnees, "une question")

    assert "ceci n'est pas verifie" not in sans_accents(bloc)
    # Un fragment stable de PROFIL plutot qu'une phrase entiere : le profil
    # change des qu'il precise quelque chose, et un test qui casse a chaque
    # precision apprend a ignorer les tests.
    assert proto.PROFIL[0][0] in bloc


# --- deux CV, et aucun ne passe devant l'autre --------------------------------

def _donnees(proto, faites_poste: int = 0, faites_alternance: int = 0) -> dict:
    cv = {}
    for nom, textes in proto.TEXTES_CV.items():
        faites = faites_poste if nom == proto.CV_POSTE else faites_alternance
        cv[nom] = [{"etape": texte, "fait": index < faites}
                   for index, texte in enumerate(textes)]
    return {"candidatures": [], "cv": cv}


def test_les_deux_cv_existent_et_different_par_l_alternance(proto) -> None:
    """Ce qu'il a tranche le 9 septembre : un CV par marche, sans hierarchie."""
    poste = proto.TEXTES_CV[proto.CV_POSTE]
    alternance = proto.TEXTES_CV[proto.CV_ALTERNANCE]

    assert len(poste) == len(alternance)
    differentes = [(a, b) for a, b in zip(poste, alternance) if a != b]
    assert len(differentes) == 1, "les deux CV ne different que sur l'alternance"
    dit_poste, dit_alternance = differentes[0]
    assert "Retirer" in dit_poste and "alternance" in dit_poste
    assert "Assumer" in dit_alternance and "alternance" in dit_alternance


def test_quand_les_deux_cv_attendent_la_meme_etape_elle_se_dit_une_fois(proto) -> None:
    """Sinon le matin repete deux fois la meme phrase, et on cesse de la lire."""
    dit = proto.action_du_jour(_donnees(proto))

    assert sum(1 for texte in dit if "Titre :" in texte) == 1
    assert "des deux CV" in dit[0]


def test_quand_ils_divergent_aucun_ne_passe_devant(proto) -> None:
    """« Postes et alternances, sans hierarchie » -- sa reponse, appliquee ici.

    Un tri arbitraire entre les deux listes la contredirait en silence chaque
    matin, et c'est le genre de contradiction que personne ne remarque.
    """
    dit = proto.action_du_jour(_donnees(proto, faites_poste=1))

    assert any(proto.NOMS_CV[proto.CV_POSTE] in texte for texte in dit)
    assert any(proto.NOMS_CV[proto.CV_ALTERNANCE] in texte for texte in dit)
    ordre = [texte for texte in dit if "CV " in texte]
    assert len(ordre) >= 2, f"les deux CV doivent etre nommes : {dit}"


def test_un_seul_cv_fini_laisse_l_autre_visible(proto) -> None:
    """Terminer le CV poste ne doit pas eteindre le rappel de l'autre."""
    dit = proto.action_du_jour(_donnees(proto, faites_poste=len(proto.TEXTES_CV[proto.CV_POSTE])))

    assert "Avancer le CV" in dit[0]
    assert proto.NOMS_CV[proto.CV_ALTERNANCE] in dit[0]


def test_le_numero_a_l_ecran_coche_la_bonne_liste(proto, capsys) -> None:
    """Les etapes sont numerotees d'un bout a l'autre des deux listes.

    Un numero qui cocherait la mauvaise ligne serait invisible : les quatre
    etapes communes ont le meme texte des deux cotes.
    """
    donnees = _donnees(proto)
    premiere_alternance = len(proto.TEXTES_CV[proto.CV_POSTE]) + 1
    proto.input = lambda _="": str(premiere_alternance)
    try:
        proto.cocher_cv(donnees)
    finally:
        del proto.input

    assert not any(e["fait"] for e in donnees["cv"][proto.CV_POSTE])
    assert donnees["cv"][proto.CV_ALTERNANCE][0]["fait"]
    assert proto.NOMS_CV[proto.CV_ALTERNANCE] in capsys.readouterr().out
