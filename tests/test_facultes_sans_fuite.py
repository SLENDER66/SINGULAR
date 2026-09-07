"""Aucune faculte qui appelle un modele ne peut faire fuir la cle.

Cette verification existait, ecrite pour `analyse` et vivant dans son fichier
de tests. Deux facultes sont nees depuis -- `offres`, puis `parle` -- et ni
l'une ni l'autre n'en a herite : elles se conformaient par imitation du code
copie, pas parce que quelque chose l'exigeait.

C'est la troisieme fois. La regle du depot dit alors d'arreter de corriger et
de rendre l'erreur impossible : la verification ne vise plus un fichier nomme,
elle trouve elle-meme toute faculte qui refuse par `AnalyseIndisponible`. La
quatrieme sera couverte le jour ou elle sera ecrite, sans que personne ait a
s'en souvenir.
"""
from __future__ import annotations

import ast
import pathlib

PAQUET = pathlib.Path(__file__).resolve().parent.parent / "singular"

#: Le seul detail d'exception tolere dans un message : un code HTTP, qui ne
#: peut porter ni la cle ni un entete.
ATTRIBUTS_PERMIS = {"status_code"}


def _facultes() -> dict[str, ast.Module]:
    """Tout module du paquet qui refuse par `AnalyseIndisponible`.

    Decouvert plutot qu'enumere : une liste ecrite a la main aurait exactement
    le defaut qu'on corrige ici.
    """
    trouves = {}
    for fichier in sorted(PAQUET.rglob("*.py")):
        source = fichier.read_text(encoding="utf-8")
        if "AnalyseIndisponible" not in source:
            continue
        arbre = ast.parse(source)
        leve = any(
            isinstance(noeud, ast.Raise)
            and isinstance(noeud.exc, ast.Call)
            and getattr(noeud.exc.func, "id", None) == "AnalyseIndisponible"
            for noeud in ast.walk(arbre)
        )
        if leve:
            trouves[str(fichier.relative_to(PAQUET.parent))] = arbre
    return trouves


def _fautes(arbre: ast.Module) -> list[str]:
    fautes = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Raise) and isinstance(noeud.exc, ast.Call)):
            continue
        if getattr(noeud.exc.func, "id", None) != "AnalyseIndisponible":
            continue
        for argument in noeud.exc.args:
            if isinstance(argument, ast.Constant):
                continue  # texte fixe : rien a interpoler
            if not isinstance(argument, ast.JoinedStr):
                fautes.append(f"ligne {noeud.lineno} : argument non litteral")
                continue
            for morceau in argument.values:
                if isinstance(morceau, ast.Constant):
                    continue
                valeur = morceau.value
                permis = (isinstance(valeur, ast.Attribute)
                          and valeur.attr in ATTRIBUTS_PERMIS)
                if not permis:
                    fautes.append(f"ligne {noeud.lineno} : {ast.dump(valeur)[:60]}")
    return fautes


def test_la_decouverte_trouve_bien_les_facultes() -> None:
    """Un test qui ne trouve plus rien a verifier passe en silence.

    Il en existe trois aujourd'hui. Si ce compte tombe, ce n'est pas au
    prochain lecteur de s'en apercevoir.
    """
    trouves = _facultes()
    assert len(trouves) >= 3, f"facultes trouvees : {sorted(trouves)}"
    assert "singular/analyse.py" in trouves


def test_aucun_message_d_erreur_ne_peut_porter_la_cle() -> None:
    """Ces messages sont lus, copies, parfois recolles dans une conversation.

    Aucun ne doit pouvoir contenir la cle, ni le texte brut d'une exception du
    SDK -- qui peut porter l'entete d'authentification selon les versions.

    Verifie sur la forme du code plutot qu'en fabriquant des pannes : une
    exception du SDK qu'on n'a pas prevue passerait entre les mailles d'un
    test qui les enumere.
    """
    fautes = {
        chemin: liste
        for chemin, arbre in _facultes().items()
        if (liste := _fautes(arbre))
    }
    assert not fautes, (
        "un message d'erreur pourrait porter la cle ou le detail brut du SDK :\n  "
        + "\n  ".join(f"{chemin} -> {liste}" for chemin, liste in fautes.items())
    )
