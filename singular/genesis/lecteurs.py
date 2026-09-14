"""Les outils : de vrais lecteurs, sur de vrais formats du dépôt.

Genesis n'invente pas un monde de jouet. Ces quatre lecteurs lisent ce que ce
dépôt contient réellement -- le JSON des vecteurs de la Notice, le TOML de
`pyproject`, les titres versionnés du changelog, l'export CSV du journal -- et
un cinquième format, `cle: valeur`, que rien ici ne sait lire aujourd'hui. C'est
celui-là que GAMMA devra apprendre.

Chacun **lève** quand le texte n'est pas du sien. C'est ce qui rend le tâtonnement
observable : un solveur qui ne sait pas quel format il tient essaie, échoue, et
l'échec est un fait enregistré, pas une exception qui remonte.

Aucun n'écrit, n'exécute, ni n'appelle quoi que ce soit.
"""
from __future__ import annotations

import csv
import io
import json
import re


class FormatRefuse(ValueError):
    """Ce texte n'est pas du format que ce lecteur sait lire."""


def lire_json(texte: str) -> dict[str, list[str]]:
    """Les clés de premier niveau d'un objet JSON, et leurs valeurs en texte."""
    try:
        charge = json.loads(texte)
    except (json.JSONDecodeError, TypeError) as erreur:
        raise FormatRefuse(f"JSON illisible : {erreur}") from None
    if not isinstance(charge, dict):
        raise FormatRefuse("JSON valide mais ce n'est pas un objet")
    return {cle: [str(valeur)] for cle, valeur in charge.items()}


def lire_toml_simple(texte: str) -> dict[str, list[str]]:
    """Les `cle = "valeur"` d'un TOML plat, sections comprises mais aplaties.

    « Simple » est dit plutôt que sous-entendu : ce lecteur ne fait pas le TOML
    complet, il fait celui de `pyproject.toml` au niveau qui sert ici. Un lecteur
    qui prétendrait faire tout le format mentirait sur ce qu'il garantit.
    """
    lignes = [ligne.strip() for ligne in texte.splitlines()]
    if not any(re.match(r'^[A-Za-z_][\w.-]*\s*=\s*"', ligne) for ligne in lignes):
        raise FormatRefuse("aucune affectation TOML entre guillemets")
    trouve: dict[str, list[str]] = {}
    for ligne in lignes:
        accord = re.match(r'^([A-Za-z_][\w.-]*)\s*=\s*"([^"]*)"', ligne)
        if accord:
            trouve.setdefault(accord.group(1), []).append(accord.group(2))
    return trouve


def lire_titres_versionnes(texte: str) -> dict[str, list[str]]:
    """Les versions déclarées par les titres `## X.Y.Z` d'un changelog."""
    versions = re.findall(r"^## (\d+\.\d+\.\d+)", texte, flags=re.MULTILINE)
    if not versions:
        raise FormatRefuse("aucun titre de version")
    return {"version": list(versions)}


def lire_csv(texte: str) -> dict[str, list[str]]:
    """Les colonnes d'un CSV à en-tête, chacune avec ses valeurs.

    Le refus est plus strict qu'un simple « ça parse » : `csv` lit à peu près
    n'importe quel texte sans se plaindre, donc un fichier d'une seule colonne
    sans séparateur serait accepté et rendrait le tâtonnement inobservable.
    """
    lignes = texte.strip().splitlines()
    if len(lignes) < 2 or "," not in lignes[0]:
        raise FormatRefuse("pas d'en-tête séparée par des virgules")
    lecteur = csv.DictReader(io.StringIO(texte))
    colonnes = lecteur.fieldnames or []
    if not colonnes:
        raise FormatRefuse("en-tête vide")
    trouve: dict[str, list[str]] = {colonne: [] for colonne in colonnes}
    for rang in lecteur:
        for colonne in colonnes:
            valeur = rang.get(colonne)
            if valeur is not None:
                trouve[colonne].append(valeur)
    return trouve


#: L'ordre dans lequel un solveur sans expérience les essaie. Il n'a rien de
#: malin : c'est l'ordre d'écriture, et c'est justement ce qu'une capacité
#: apprise remplace.
TOUS = (
    ("json", lire_json),
    ("toml", lire_toml_simple),
    ("titres_versionnes", lire_titres_versionnes),
    ("csv", lire_csv),
)


__all__ = ["TOUS", "FormatRefuse", "lire_csv", "lire_json", "lire_titres_versionnes",
           "lire_toml_simple"]
