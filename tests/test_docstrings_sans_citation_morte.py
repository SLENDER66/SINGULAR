"""Une docstring qui cite un nom disparu envoie le lecteur suivant nulle part.

`_calibration_item` a expliqué pendant des semaines que sa règle se lisait « en
dessous de `CALIBRATION_CERTAIN` verdicts ». La constante n'existait plus : elle
avait été remplacée par un calcul exact — un écart, et la probabilité que le
hasard seul le produise. La phrase décrivait donc une règle que le code
n'appliquait pas, dans le fichier qui est justement le domicile unique des
règles de la Notice.

C'est le défaut le moins visible du dépôt : rien ne casse, aucun test ne rougit,
et la prochaine session lit une explication fausse écrite avec autorité. Elle
corrigera le code pour le faire correspondre à la phrase.

Ce test lit les docstrings et vérifie que chaque nom en MAJUSCULES cité entre
accents graves existe vraiment dans son fichier. Il ne juge pas ce que la phrase
dit — personne ne peut — il vérifie seulement qu'elle parle de quelque chose.
"""
from __future__ import annotations

import ast
import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Les fichiers qui portent les règles : le moteur et ses outils.
SOURCES = sorted((RACINE / "singular").rglob("*.py")) + sorted((RACINE / "tools").rglob("*.py"))

#: `CALIBRATION_CERTAIN`, `LATE_DAYS` : un nom de constante entre accents graves.
CITATION = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")

#: Des majuscules qui ne sont pas des noms du fichier.
HORS_SUJET = {"HALT", "OBSERVE", "JSON", "HTTP", "HTTPS", "SQLITE", "UTC", "API", "URL", "CSV"}


def _noms_definis(arbre: ast.AST) -> set[str]:
    """Tout ce qu'un fichier nomme : ses variables, ses fonctions, ses attributs.

    Large exprès. Le test cherche la citation morte, pas la citation impure : un
    faux positif ferait désactiver le test, ce qui est le seul échec possible ici.
    """
    noms: set[str] = set()
    for node in ast.walk(arbre):
        if isinstance(node, ast.Name):
            noms.add(node.id)
        elif isinstance(node, ast.Attribute):
            noms.add(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            noms.add(node.name)
        elif isinstance(node, ast.alias):
            noms.add((node.asname or node.name).split(".")[0])
    return noms


def _citations_mortes(source: pathlib.Path) -> list[tuple[str, str]]:
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    definis = _noms_definis(arbre)
    mortes = []
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        doc = ast.get_docstring(node)
        if not doc:
            continue
        for cite in CITATION.findall(doc):
            if cite not in definis and cite not in HORS_SUJET:
                mortes.append((getattr(node, "name", "<module>"), cite))
    return mortes


def test_aucune_docstring_ne_cite_un_nom_disparu() -> None:
    mortes = {source.relative_to(RACINE): trouvees
              for source in SOURCES if (trouvees := _citations_mortes(source))}
    assert not mortes, (
        "une docstring cite un nom qui n'existe plus :\n"
        + "\n".join(f"  {fichier} — {ou} cite {quoi}"
                    for fichier, liste in mortes.items() for ou, quoi in liste)
        + "\nRenomme la citation, ou réécris la phrase pour dire ce que le code fait.")


def test_le_lecteur_verrait_une_citation_morte(tmp_path) -> None:
    """Le témoin : sans lui, un analyseur qui ne lit rien passerait au vert."""
    faux = tmp_path / "faux.py"
    faux.write_text('"""Voir `DISPARU` pour le seuil."""\nVIVANT = 1\n', encoding="utf-8")
    assert _citations_mortes(faux) == [("<module>", "DISPARU")]

    vrai = tmp_path / "vrai.py"
    vrai.write_text('"""Voir `VIVANT` pour le seuil."""\nVIVANT = 1\n', encoding="utf-8")
    assert _citations_mortes(vrai) == []


def test_le_scan_regarde_bien_le_moteur() -> None:
    """Et le témoin du témoin : une liste de fichiers vide ne garderait rien."""
    assert RACINE / "singular/sage/notice.py" in SOURCES
    assert len(SOURCES) > 50
