"""Les commandes qu'on lui donne doivent marcher dans SA fenêtre.

Deux fois dans la même journée, une commande écrite ici a échoué chez lui pour
une raison qui n'avait rien à voir avec SINGULAR :

- `set ANTHROPIC_API_KEY=...` ne pose la variable dans aucun de ses terminaux.
  La clé n'était pas posée, le serveur démarrait sans elle, et le bouton disait
  « coupée » sans que rien relie les deux.
- `pip install -e '.[analyse]'` suppose que `pip` est dans le PATH et vise le
  même Python que celui qui lance SINGULAR. Ni l'un ni l'autre n'est acquis.

À chaque fois l'échec est silencieux ou trompeur, et il le découvre seul, sans
moyen de faire le lien. C'est le pire genre de faute : elle ne casse pas le
code, elle casse la personne qui suit les instructions.

Sa fenêtre a changé de machine le 10 septembre 2026 : le Mac remplace le PC,
donc c'est `zsh`. Les deux règles de ce fichier ont survécu au changement sans
être touchées, et ce n'est pas un hasard — elles interdisent une forme qui ne
marche nulle part, pas une forme qui marche ailleurs. C'est
`tests/test_documentation_is_current.py` qui porte ce qui dépend de la machine,
et lui a dû changer de camp.
"""
from __future__ import annotations

import ast
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
    """`python3 -m pip` vise le Python qui lance SINGULAR, et existe partout.

    `pip` seul suppose deux choses fausses : qu'il est dans le PATH, et qu'il
    installe pour le bon interpréteur. Sur un Mac ou plusieurs Python
    cohabitent -- celui du systeme, celui de python.org, celui de Homebrew --
    la seconde est la plus couteuse : l'installation reussit, et SINGULAR ne
    trouve rien.
    """
    # `\s+\S` exige un argument : c'est ce qui distingue une commande d'une
    # mention en prose -- « aucun `pip install` » ferme son accent grave tout
    # de suite et n'installe rien.
    fautes = [f"{chemin}:{numero}" for chemin, numero, ligne in _lignes()
              if re.search(r"(?<!-m )\bpip install\s+\S", ligne)]
    assert not fautes, (
        "ces lignes disent « pip install » sans « python -m » :\n  " + "\n  ".join(fautes))


def test_aucune_commande_ne_pose_une_variable_a_la_facon_de_cmd() -> None:
    """`set X=...` ne pose la variable dans aucun de ses terminaux.

    La forme de `zsh`, son terminal depuis que le Mac remplace le PC, est
    `export X="..."`. La mention de `set` reste permise quand elle est là pour
    lui faire reconnaître son erreur -- elle est alors nommée comme la commande
    d'une autre fenêtre.
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


# --- ce que le programme lui donne a taper -----------------------------------

#: `python` sans le 3, suivi de ce qui en fait une commande.
#:
#: La regle etait ecrite pour les documents et pas pour le programme. Sur le
#: tout premier ecran d'une machine neuve -- « Journal vide » -- il lisait
#: « `python -m singular add` pour commencer », et `python` seul n'existe plus
#: depuis macOS 12.3 : « command not found », sur la premiere commande de sa
#: premiere journee.
PYTHON_NU = re.compile(r"(?<!3)\bpython (?=-m|tools/|proto/|examples/)")

#: Ce que le programme affiche, ou envoie a l'ecran du telephone.
AFFICHE_PAR_LE_PROGRAMME = [
    *sorted((RACINE / "singular").rglob("*.py")),
    *sorted((RACINE / "proto").rglob("*.py")),
    RACINE / "singular/sage/web/index.html",
    RACINE / "singular/sage/web/app.js",
]


def _messages(chemin: pathlib.Path) -> list[tuple[int, str]]:
    """Les chaines affichees. Docstrings exclues : elles ne sortent pas a l'ecran.

    Meme decoupage que `test_windows_console.py`, et pour la meme raison : une
    docstring qui raconte l'histoire d'une commande n'est pas une commande
    donnee a taper, et la confondre ferait crier au loup.
    """
    if chemin.suffix != ".py":
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        return [(numero + 1, ligne) for numero, ligne in enumerate(lignes)
                if PYTHON_NU.search(ligne)]

    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    docstrings = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            premier = noeud.body[0] if noeud.body else None
            if isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant) \
                    and isinstance(premier.value.value, str):
                docstrings.add(id(premier.value))
    return [(noeud.lineno, noeud.value) for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)
            and id(noeud) not in docstrings and PYTHON_NU.search(noeud.value)]


def test_aucun_message_ne_lui_donne_python_sans_le_trois() -> None:
    fautes = [f"{chemin.relative_to(RACINE)}:{numero} — {' '.join(str(texte).split())[:70]}"
              for chemin in AFFICHE_PAR_LE_PROGRAMME
              for numero, texte in _messages(chemin)]

    assert not fautes, (
        "ces messages lui donnent `python` a taper :\n  " + "\n  ".join(fautes)
        + "\n  Depuis macOS 12.3 la commande n'existe plus : elle rend "
        "« command not found », ce qui ressemble a un outil casse.")


def test_le_scan_lit_bien_les_messages() -> None:
    """Le temoin : un analyseur qui ne trouve rien passerait au vert.

    Il verifie aussi les deux versants du decoupage -- un message est vu, une
    docstring ne l'est pas -- parce que c'est la seule chose qui distingue ce
    test d'un `grep`.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as dossier:
        faux = pathlib.Path(dossier) / "faux.py"
        faux.write_text('"""Voir python -m singular add pour l\'histoire."""\n'
                        'def dire():\n'
                        '    print("tape python -m singular add")\n', encoding="utf-8")
        trouves = _messages(faux)

    assert len(trouves) == 1, f"un message, pas la docstring : {trouves}"
    assert "tape python -m" in trouves[0][1]
    assert len(AFFICHE_PAR_LE_PROGRAMME) > 10


# --- une commande citee doit exister -----------------------------------------
#
# L'orthographe est gardee au-dessus : `python3`, pas `python`. Restait l'autre
# moitie, jamais verifiee -- la commande existe-t-elle encore ? Ses pages citent
# des dizaines de `python3 -m singular ...` avec leurs options, et rien ne les
# reliait au parseur. Le defaut est le meme que celui des commandes PowerShell
# restees apres le passage au Mac : la page a raison hier, elle a tort demain, et
# c'est lui qui l'apprend en tapant.
#
# Le parseur est lu sur l'arbre, pas lance : `--help` demanderait d'importer le
# paquet, donc d'installer ses dependances, et ce test doit tourner partout.

#: `python3 -m singular parle --blanc --modele x` : la sous-commande, puis ses options.
COMMANDE_CITEE = re.compile(r"python3 -m singular\s+([a-z]+)((?:\s+--[a-z-]+)*)")


def _parseur_declare() -> dict[str, set[str]]:
    """Chaque sous-commande de `__main__.py` et les options qu'elle accepte."""
    source = (RACINE / "singular" / "__main__.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)

    nom_par_variable: dict[str, str] = {}
    declare: dict[str, set[str]] = {}
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Assign) and isinstance(noeud.value, ast.Call)):
            continue
        appel = noeud.value
        if not (isinstance(appel.func, ast.Attribute) and appel.func.attr == "add_parser"):
            continue
        if not (appel.args and isinstance(appel.args[0], ast.Constant)):
            continue
        if isinstance(noeud.targets[0], ast.Name):
            nom_par_variable[noeud.targets[0].id] = appel.args[0].value
            declare[appel.args[0].value] = set()

    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)):
            continue
        if noeud.func.attr != "add_argument" or not isinstance(noeud.func.value, ast.Name):
            continue
        commande = nom_par_variable.get(noeud.func.value.id)
        if commande and noeud.args and isinstance(noeud.args[0], ast.Constant):
            declare[commande].add(noeud.args[0].value)
    return declare


def test_toute_commande_citee_dans_ses_pages_existe() -> None:
    declare = _parseur_declare()
    assert declare, "le parseur doit etre lu, pas un dictionnaire vide"

    fautes = []
    citations = 0
    for chemin in LUS_PAR_LUI:
        if chemin.suffix != ".md":
            continue
        texte = chemin.read_text(encoding="utf-8")
        for commande, options in COMMANDE_CITEE.findall(texte):
            citations += 1
            if commande not in declare:
                fautes.append(f"{chemin.name} : `{commande}` n'est pas une sous-commande")
                continue
            for option in re.findall(r"--[a-z-]+", options):
                if option not in declare[commande]:
                    fautes.append(f"{chemin.name} : `{commande} {option}` n'existe pas")

    assert citations, "aucune commande lue dans ses pages : l'expression ne reconnait plus rien"
    assert not fautes, (
        "ces commandes sont ecrites dans ses pages et n'existent pas :\n  "
        + "\n  ".join(sorted(set(fautes)))
        + "\n  Il les tape et lit une erreur d'argparse, en anglais.")


def test_le_lecteur_du_parseur_attraperait_une_commande_disparue() -> None:
    """Le temoin : sans lui, le test au-dessus passerait sur un parseur mal lu."""
    declare = _parseur_declare()

    assert "parle" in declare and "--blanc" in declare["parle"]
    assert "list" in declare and "--status" in declare["list"]
    assert "--oubli" not in declare.get("review", set()), (
        "une option d'une sous-commande ne doit pas etre attribuee a une autre")
    assert COMMANDE_CITEE.findall("python3 -m singular parle --blanc") == [("parle", " --blanc")]
