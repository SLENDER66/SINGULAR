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
