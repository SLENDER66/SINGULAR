"""Les six rangs s'écrivent pareil dans le terminal et dans l'app.

`Tier.label` existe pour ça, et sa docstring le dit : « Les valeurs stockées
sont sans accent, pour qu'une base écrite hier reste lisible demain quel que
soit l'encodage. Ce qu'on montre à l'écran, lui, doit être le mot juste. »

Le terminal ne l'utilisait nulle part. Il affichait `tier.value`, c'est-à-dire
la valeur de stockage : `Stabilite`, `Capacites`, `Opportunites`, `Liberte`. La
même journée, sur son téléphone, l'app affichait `Stabilité` et `Capacités`,
parce que `sage/server.py` envoie bien `tier_label`. Quatre des six rangs de sa
constitution s'écrivaient de deux façons selon l'écran où il les lisait.

Trouvé en jouant `add` sur un dossier personnel vide : le menu des rangs est le
troisième écran d'une machine neuve.

La règle que ce fichier tient est plus large que le bug, et elle se découvre
toute seule dans le code : **une énumération qui prend la peine de déclarer un
`label` ne doit jamais être affichée par sa valeur.** Le garde-fou lit les
classes du journal, retient celles qui ont la propriété, et refuse leur
`.value` à l'intérieur d'une chaîne formatée. Le jour où une septième
énumération gagne un `label`, elle est protégée sans qu'on y pense.

Une valeur hors chaîne formatée reste permise, et c'est nécessaire :
`report["by_tier"].get(tier.value)` cherche une clé, il n'écrit rien.
`durable.py` affiche `status.value` d'un statut moteur qui n'a pas de `label`,
et n'est pas concerné.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from singular import journal as _journal
from singular.journal import Tier

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Les modules dont les chaînes formatées finissent sous ses yeux.
PARLENT_A_L_ECRAN = ("singular/__main__.py", "singular/sage/server.py", "singular/analyse.py")


def _enums_avec_label() -> set[str]:
    """Les attributs qui portent une énumération munie d'un `label`.

    Déduit du code plutôt que recopié : le nom de la classe en minuscules est
    le nom sous lequel elle se lit partout (`entry.tier`, `entry.reversibility`).
    """
    noms = set()
    for nom, objet in vars(_journal).items():
        if isinstance(objet, type) and isinstance(getattr(objet, "label", None), property):
            noms.add(nom.lower())
    return noms


def _valeurs_affichees(source: str) -> list[tuple[int, str]]:
    fautes = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.JoinedStr):
            continue
        for morceau in node.values:
            if not isinstance(morceau, ast.FormattedValue):
                continue
            for interne in ast.walk(morceau.value):
                if not (isinstance(interne, ast.Attribute) and interne.attr == "value"):
                    continue
                base = ast.unparse(interne.value).split(".")[-1]
                if base in _enums_avec_label():
                    fautes.append((interne.lineno, ast.unparse(morceau.value)))
    return fautes


def test_le_journal_declare_des_labels():
    """Sans ça le garde-fou ci-dessous passerait en ne cherchant rien."""
    assert "tier" in _enums_avec_label()
    assert isinstance(Tier.STABILITE.label, str)


@pytest.mark.parametrize("chemin", PARLENT_A_L_ECRAN)
def test_aucune_valeur_de_stockage_a_l_ecran(chemin):
    fautes = _valeurs_affichees((ROOT / chemin).read_text(encoding="utf-8"))
    assert not fautes, (
        f"{chemin} affiche une valeur de stockage au lieu du mot juste :\n"
        + "\n".join(f"  ligne {ligne} : {code}" for ligne, code in fautes)
        + "\nUtilise `.label` -- c'est ce pour quoi la propriete existe."
    )


def test_les_six_rangs_s_ecrivent_avec_leurs_accents():
    """Le menu de `add` les liste ; c'est cette liste qui était fausse."""
    ecrits = [tier.label for tier in Tier]
    assert ecrits == ["Stabilité", "Revenus", "Capacités",
                      "Opportunités", "Patrimoine", "Liberté"]
    #: Et la valeur stockée, elle, reste sans accent : une base écrite hier
    #: doit se relire demain quel que soit l'encodage.
    assert all(tier.value.isascii() for tier in Tier)
