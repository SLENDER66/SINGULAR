"""La spécification maîtresse est citée telle quelle, et son annexe est vérifiée.

`SPECIFICATION.md` contient deux textes de nature opposée, et ce fichier les
garde différemment.

**Le corps, sections 0 à 100, est du fondateur.** Il se cite, il ne se reformule
pas : une session future qui « améliorerait » une formulation détruirait la seule
copie durable d'un texte qui commande le code. Ce qui est testé ici est donc
qu'aucune section n'a disparu -- pas leur contenu, qu'aucun test ne peut juger.

**L'annexe est de moi, et elle affirme des faits.** Elle dit ce qui existe, ce
qui n'existe pas, et nomme les commandes et les tests qui le prouvent. C'est
exactement la classe d'erreur que `tests/test_documentation_is_current.py`
raconte : une documentation fausse ne casse rien, elle envoie simplement le
lecteur suivant au mauvais endroit, et on ne l'apprend qu'en perdant une séance.
Chaque chemin et chaque commande qu'elle cite sont donc confrontés au dépôt.

Ce qui n'est pas testable reste à la charge du lecteur : qu'une section soit
justement classée « n'existe pas » est un jugement, pas une propriété de l'arbre.
Le registre de réalité, lui, est dérivé -- c'est `tools/etat_reel.py`, et
`tests/test_etat_reel.py` le garde.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from singular.__main__ import build_parser

RACINE = pathlib.Path(__file__).resolve().parent.parent
SPECIFICATION = RACINE / "SPECIFICATION.md"

#: L'annexe commence à ce titre. Tout ce qui précède est le texte du fondateur.
DEBUT_ANNEXE = "# ANNEXE — CE QUE CETTE SPÉCIFICATION A PRODUIT"


def _texte() -> str:
    return SPECIFICATION.read_text(encoding="utf-8")


def _annexe() -> str:
    texte = _texte()
    coupe = texte.find(DEBUT_ANNEXE)
    assert coupe != -1, (
        "l'annexe a disparu de SPECIFICATION.md : le texte du fondateur se "
        "retrouve seul, sans rien qui sépare la vision de ce qui est construit")
    return texte[coupe:]


def test_le_corps_de_la_specification_est_complet() -> None:
    """Les cent-et-une sections du fondateur sont là, de 0 à 100.

    Une section perdue dans une édition ne casserait rien et ne se verrait pas :
    c'est la raison d'être de ce test. Il compte des titres qu'il dérive du
    fichier lui-même, il n'écrit aucun total à la main.
    """
    texte = _texte()
    presentes = set()
    for motif in (r"^## (\d+)\. ", r"^(\d+)\. [A-ZÉÈÀÎÔÛ]"):
        presentes |= {int(n) for n in re.findall(motif, texte, flags=re.MULTILINE)}

    manquantes = sorted(set(range(0, 101)) - presentes)
    assert not manquantes, (
        f"ces sections du fondateur ont disparu de SPECIFICATION.md : {manquantes}. "
        "Une spécification se cite, elle ne se réécrit pas.")


def test_la_specification_dit_qu_elle_n_est_pas_l_etat_du_depot() -> None:
    """Sans cette séparation, le document devient la liste de ce qu'on croit avoir.

    C'est la lecture que sa propre section 98 impose, et la panne qu'elle décrit :
    un plan lu comme un inventaire.
    """
    entete = _texte()[:_texte().find(DEBUT_ANNEXE)]
    assert "98" in entete, "l'en-tête ne renvoie plus à la section qui gouverne sa lecture"
    assert "tools/etat_reel.py" in entete, (
        "l'en-tête ne renvoie plus vers le registre : un lecteur pourrait croire "
        "que ce document décrit l'état réel")


def _chemins_cites() -> set[str]:
    """Les chemins du dépôt que l'annexe nomme, entre accents graves."""
    motif = re.compile(r"`([A-Za-z_0-9./]+\.(?:py|md|json))`")
    return set(motif.findall(_annexe()))


def test_chaque_chemin_cite_par_l_annexe_existe() -> None:
    """Un chemin mort est le premier signe d'une annexe figée."""
    cites = _chemins_cites()
    assert cites, "l'annexe ne cite plus aucun fichier : elle n'est plus vérifiable"

    absents = sorted(chemin for chemin in cites if not (RACINE / chemin).exists())
    assert not absents, f"l'annexe cite des chemins qui n'existent pas : {absents}"


def test_chaque_commande_citee_par_l_annexe_existe() -> None:
    """Renvoyer le fondateur vers une commande disparue lui coûte une séance."""
    commandes = set(re.findall(r"python3 -m singular (\w+)", _annexe()))
    assert commandes, "l'annexe ne renvoie plus vers aucune commande"

    parser = build_parser()
    connues = {nom for action in parser._actions
               if getattr(action, "choices", None) for nom in action.choices}
    inconnues = sorted(commandes - connues)
    assert not inconnues, f"l'annexe cite des commandes qui n'existent pas : {inconnues}"


def test_chaque_outil_cite_par_l_annexe_est_executable() -> None:
    """Un outil cité doit au moins être un module Python valide."""
    import ast

    outils = sorted(chemin for chemin in _chemins_cites() if chemin.startswith("tools/"))
    assert outils, "l'annexe ne renvoie plus vers aucun outil"

    for outil in outils:
        source = (RACINE / outil).read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as erreur:  # pragma: no cover - ne doit jamais arriver
            pytest.fail(f"{outil} est cité par l'annexe et ne compile pas : {erreur}")


def test_l_annexe_nomme_la_contradiction_au_lieu_de_la_lisser() -> None:
    """La section 70 interdit de supprimer une contradiction pour conclure.

    L'annexe en porte une, et c'est la plus importante : la section 44 prévoit
    une validation humaine que la frontière ne fait pas -- elle refuse à la porte.
    Une session future qui trouverait le document plus propre sans ce paragraphe
    aurait supprimé exactement ce que la section 70 protège. Ce test est le prix
    de cette suppression.
    """
    annexe = _annexe()
    assert "44" in annexe and "contradiction" in annexe.lower(), (
        "l'annexe ne nomme plus la contradiction entre la section 44 et la "
        "frontière construite : elle a été lissée")
    assert "décision du fondateur" in annexe, (
        "la contradiction est nommée mais ne dit plus à qui elle revient : "
        "une session ne tranche pas cela seule")
