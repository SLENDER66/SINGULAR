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
        "cv": [{"etape": "Changer le titre", "fait": False},
               {"etape": "Traduire trois chantiers", "fait": True}],
    }

    bloc = proto.texte_pour_claude(donnees, "relis le titre de mon CV")

    assert "BTS Fluides Energies Domotique" in bloc     # qui je suis
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
        "cv": [{"etape": "Changer le titre", "fait": True}],
    }

    bloc = proto.texte_pour_claude(donnees, "et maintenant ?")

    assert "Refusee SA" not in bloc
    assert "je n'ai pas encore commence" in bloc
    assert "Mon CV est termine." in bloc


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

    assert [e["etape"] for e in donnees["cv"]] == proto.ETAPES_CV


def test_une_etape_deja_cochee_interdit_la_mise_a_jour(proto) -> None:
    """Le travail déjà fait vaut mieux qu'une liste à jour : on ne l'efface pas."""
    proto.FICHIER.parent.mkdir(parents=True, exist_ok=True)
    proto.FICHIER.write_text(json.dumps({
        "candidatures": [],
        "cv": [{"etape": "Une etape d'avant", "fait": True},
               {"etape": "Une autre", "fait": False}],
    }), encoding="utf-8")

    donnees = proto.charger()

    assert [e["etape"] for e in donnees["cv"]] == ["Une etape d'avant", "Une autre"]


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


def test_une_deduction_est_affichee_comme_non_verifiee(proto) -> None:
    """Si une déduction entre quand même, elle ne doit pas voyager déguisée."""
    donnees = {"candidatures": [], "cv": [{"etape": "x", "fait": True}]}
    veritable = list(proto.PROFIL)
    try:
        proto.PROFIL.append(("Il vise plutot l'industriel.", proto.DEDUIT))
        bloc = proto.texte_pour_claude(donnees, "une question")
    finally:
        proto.PROFIL[:] = veritable

    assert "Ceci n'est pas verifie" in bloc
    assert "Il vise plutot l'industriel." in bloc
    ligne = next(l for l in bloc.splitlines() if "industriel" in l)
    assert ligne.startswith("- "), "une deduction doit etre listee a part, pas fondue dans le profil"


def test_un_fait_dit_n_est_pas_marque_comme_incertain(proto) -> None:
    """L'inverse : signaler tout affaiblirait ce que le signal veut dire."""
    donnees = {"candidatures": [], "cv": [{"etape": "x", "fait": True}]}

    bloc = proto.texte_pour_claude(donnees, "une question")

    assert "Ceci n'est pas verifie" not in bloc
    assert "centrales de traitement d'air double flux" in bloc
