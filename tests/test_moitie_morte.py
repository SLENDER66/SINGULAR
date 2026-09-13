"""Une moitie de garde qu'aucune entree ne peut distinguer n'est pas un garde.

`tools/gardes_sans_test.py` neutralise une moitie a la fois d'un garde compose.
Trois fois de suite, la moitie neutralisee a **survecu** sans qu'aucun test
rougisse -- non pas parce qu'un temoin manquait, mais parce qu'il n'en existe
aucun : l'autre moitie repond deja vrai sur toutes les entrees qui rendraient
celle-la vraie.

1. `validated_execution.py` : `store is None or not hasattr(store, "path")`.
   `None` n'a pas d'attribut `path`, donc la seconde moitie refuse deja `None`.
2. `durable.py` : `rows is not None and ...` derriere un `SELECT COUNT(*)`, qui
   renvoie toujours une ligne.
3. `mission_runtime.py` : `legacy is None or legacy != native[...]`, mesure le
   jour meme -- effacer la liaison rend les deux moities vraies en meme temps.

Les trois sont de la meme famille : **une comparaison ne peut pas etre vraie et
son operande valoir `None`**, des lors que l'autre cote n'est jamais `None`.
`X is None or X != Y` vaut donc exactement `X != Y`, et `X is not None and
X == Y` vaut exactement `X == Y`.

Troisieme passage, donc on arrete de corriger : ce fichier echoue si le motif
reapparait, n'importe ou dans le depot. Au moment ou il a ete ecrit, il a
retire les trois derniers sites :

    singular/execution.py:464             actual is None or actual != expected
    singular/learning_review_queue.py:79  persisted is None or persisted != outcome
    singular/mission_runtime.py:161       legacy is None or legacy != native[...]

Si une comparaison doit vraiment traiter `None` a part -- parce que l'autre
operande peut l'etre aussi -- elle s'ecrit en deux instructions, avec le refus
que chaque cas merite. Ce n'est pas une contrainte : c'est ce qu'un lecteur
comprendra, la ou le `or` cachait qu'un des deux cas n'arrivait jamais.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Tout le Python du depot. Le motif n'est pas plus acceptable dans un test que
#: dans le moteur : il y ferait croire qu'un cas est couvert.
DOSSIERS = ("singular", "tests", "tools", "proto")


def _comparaison(noeud: ast.AST, operateur: type[ast.cmpop]) -> ast.Compare | None:
    """Le noeud s'il est `a <operateur> b` et rien de plus, sinon `None`.

    Une comparaison chainee (`a < b < c`) porte plusieurs operateurs : on la
    laisse passer, le raisonnement de ce fichier ne tient pas dessus.
    """
    if isinstance(noeud, ast.Compare) and len(noeud.ops) == 1 and isinstance(noeud.ops[0], operateur):
        return noeud
    return None


def _est_none(noeud: ast.AST) -> bool:
    return isinstance(noeud, ast.Constant) and noeud.value is None


def moities_mortes(source: str) -> list[tuple[int, str]]:
    """Les `or`/`and` ou un test de `None` ne peut pas decider seul.

    Dans un `or` : `X is None` a cote de `X != Y`. Dans un `and` :
    `X is not None` a cote de `X == Y`. Les deux operandes sont compares par
    leur arbre, pas par leur texte, pour que `native["a"]` et `native ["a"]`
    soient la meme expression.
    """
    trouves: list[tuple[int, str]] = []
    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.BoolOp):
            continue
        ou = isinstance(noeud.op, ast.Or)
        garde, voulu = (ast.Is, ast.NotEq) if ou else (ast.IsNot, ast.Eq)
        for i, gauche in enumerate(noeud.values):
            test = _comparaison(gauche, garde)
            if test is None or not _est_none(test.comparators[0]):
                continue
            cible = ast.dump(test.left)
            for j, droite in enumerate(noeud.values):
                if i == j:
                    continue
                autre = _comparaison(droite, voulu)
                if autre is None or _est_none(autre.comparators[0]):
                    continue
                if ast.dump(autre.left) == cible:
                    trouves.append((noeud.lineno, "or" if ou else "and"))
    return trouves


@pytest.mark.parametrize("dossier", DOSSIERS)
def test_aucun_garde_ne_porte_une_moitie_que_rien_ne_distingue(dossier):
    coupables = []
    for chemin in sorted((RACINE / dossier).rglob("*.py")):
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        for ligne, operateur in moities_mortes("\n".join(lignes)):
            coupables.append(f"{chemin.relative_to(RACINE)}:{ligne} ({operateur})  {lignes[ligne - 1].strip()}")
    assert not coupables, (
        "Une moitie de ce garde ne peut jamais decider seule : la comparaison "
        "repond deja pour elle. Garde la comparaison seule, ou, si `None` doit "
        "etre traite a part, ecris-le en deux instructions.\n" + "\n".join(coupables)
    )


#: Les trois sites retires le jour ou ce fichier a ete ecrit, recopies pour que
#: le detecteur soit mesure sur ce qu'il pretend avoir attrape.
RETIRES = [
    "if actual is None or actual != expected:\n    raise PermissionError('x')",
    "if persisted is None or persisted != outcome:\n    raise PermissionError('x')",
    "if legacy is None or legacy != native['action_fingerprint']:\n    raise ValueError('x')",
]


@pytest.mark.parametrize("source", RETIRES)
def test_le_detecteur_attrape_ce_qui_vient_d_etre_retire(source):
    assert moities_mortes(source) == [(1, "or")]


def test_le_detecteur_attrape_aussi_la_forme_en_and():
    assert moities_mortes("if x is not None and x == y:\n    pass") == [(1, "and")]


@pytest.mark.parametrize(
    "source",
    [
        # `Y` vaut `None` : les deux moities ne disent pas la meme chose, celle
        # qui teste `None` decide seule quand l'autre repond faux.
        "if x is None or x != None:\n    pass",
        # `is not None` a cote de `!=` : si `x` est `None`, le `and` repond faux
        # la ou la comparaison seule repondrait vrai. Moitie portante.
        "if x is not None and x != y:\n    pass",
        # Deux expressions differentes : aucune ne repond pour l'autre.
        "if x is None or z != y:\n    pass",
        # Le meme motif sous un `and` ne se simplifie pas : `x is None and
        # x != y` est toujours faux, c'est un autre defaut que celui-ci.
        "if x is None and x != y:\n    pass",
    ],
)
def test_le_detecteur_ne_crie_pas_sur_un_garde_dont_les_deux_moities_portent(source):
    assert moities_mortes(source) == []
