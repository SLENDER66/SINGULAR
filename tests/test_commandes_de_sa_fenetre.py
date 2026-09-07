"""Les commandes qu'on lui donne doivent marcher dans SA fenêtre.

Deux fois dans la même journée, une commande écrite ici a échoué chez lui pour
une raison qui n'avait rien à voir avec SINGULAR :

- `set ANTHROPIC_API_KEY=...` ne fait rien en PowerShell, qui est son terminal.
  La clé n'était pas posée, le serveur démarrait sans elle, et le bouton disait
  « coupée » sans que rien relie les deux.
- `pip install -e '.[analyse]'` suppose que `pip` est dans le PATH et vise le
  même Python que celui qui lance SINGULAR. Sur Windows, ni l'un ni l'autre
  n'est acquis.

À chaque fois l'échec est silencieux ou trompeur, et il le découvre seul, sans
moyen de faire le lien. C'est le pire genre de faute : elle ne casse pas le
code, elle casse la personne qui suit les instructions.

Ce fichier tient la règle plutôt que de compter sur la vigilance : toute
commande écrite pour lui doit fonctionner dans `cmd`, dans PowerShell et dans
un terminal Unix, sans être réécrite.
"""
from __future__ import annotations

import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Ce qu'il lit : ses fichiers à lui, et les messages que le programme affiche.
LUS_PAR_LUI = [
    RACINE / "A_FAIRE.md",
    RACINE / "USAGE.md",
    RACINE / "README.md",
    RACINE / "PROMPT_NOUVELLE_CONVERSATION.md",
    *sorted((RACINE / "singular").rglob("*.py")),
]


def _lignes() -> list[tuple[str, int, str]]:
    trouvees = []
    for fichier in LUS_PAR_LUI:
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            trouvees.append((str(fichier.relative_to(RACINE)), numero, ligne))
    return trouvees


def test_la_lecture_voit_bien_les_fichiers() -> None:
    """Un test qui ne lit plus rien passerait en silence."""
    lignes = _lignes()
    assert len(lignes) > 500
    assert any("A_FAIRE.md" == chemin for chemin, _, _ in lignes)


def test_aucune_commande_pip_ne_suppose_le_chemin_ni_l_interpreteur() -> None:
    """`python -m pip` vise le Python qui lance SINGULAR, et existe partout.

    `pip` seul suppose deux choses fausses sur Windows : qu'il est dans le
    PATH, et qu'il installe pour le bon interpréteur.
    """
    # `\s+\S` exige un argument : c'est ce qui distingue une commande d'une
    # mention en prose -- « aucun `pip install` » ferme son accent grave tout
    # de suite et n'installe rien.
    fautes = [f"{chemin}:{numero}" for chemin, numero, ligne in _lignes()
              if re.search(r"(?<!-m )\bpip install\s+\S", ligne)]
    assert not fautes, (
        "ces lignes disent « pip install » sans « python -m » :\n  " + "\n  ".join(fautes))


def test_aucune_commande_ne_pose_une_variable_a_la_facon_de_cmd() -> None:
    """`set X=...` ne fait rien d'utile en PowerShell, qui est son terminal.

    La forme PowerShell est `$env:X = "..."`. La mention de `set` reste permise
    quand elle est là pour lui faire reconnaître son erreur -- elle est alors
    nommée comme la commande de l'autre fenêtre.
    """
    fautes = []
    for chemin, numero, ligne in _lignes():
        if not re.search(r"^\s*(?:```\w*\s*)?set\s+[A-Z_]+=", ligne):
            continue
        if "cmd" in ligne.lower():
            continue  # nommée comme telle : c'est ce qui la rend lisible
        fautes.append(f"{chemin}:{numero} : {ligne.strip()}")

    assert not fautes, (
        "ces lignes posent une variable à la façon de `cmd`, sans le dire :\n  "
        + "\n  ".join(fautes))
