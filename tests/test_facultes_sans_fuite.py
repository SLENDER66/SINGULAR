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

import pytest

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


# --- ce qui s'echappe compte autant que ce qu'on ecrit ------------------------

def _appels():
    """Chaque faculte, appelable avec un client injecte.

    Une table ecrite a la main -- les signatures different, on ne les devine
    pas -- mais gardee par `test_la_table_couvre_toutes_les_facultes` : une
    faculte de plus fait tomber ce test tant qu'elle n'est pas branchee ici.
    """
    from singular.analyse import analyser
    from singular.offres import chercher
    from singular.parle import Conversation, repondre

    return {
        "singular/analyse.py": lambda client: analyser(
            {"headline": "Notice.", "generated_at": "2026-09-07T09:00:00+00:00",
             "items": [], "report": {"decisions": 0}},
            client=client,
        ),
        "singular/offres.py": lambda client: chercher(client=client),
        "singular/parle.py": lambda client: repondre(
            "bonjour", "rapport", Conversation(pathlib.Path("/nonexistent/fil.json")),
            client=client,
        ),
    }


class ClientQuiEchoue:
    """Un SDK qui leve une erreur dont le texte porterait la cle.

    `APIResponseValidationError` est le cas reel : elle descend d'`APIError`
    sans passer par `APIStatusError` ni `APIConnectionError`, donc elle
    traversait les quatre `except` de chaque faculte.
    """

    def __init__(self, exception: BaseException) -> None:
        self._exception = exception

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        raise self._exception


def test_la_table_couvre_toutes_les_facultes() -> None:
    """Sinon la faculte suivante serait verifiee sur la forme et pas sur l'acte."""
    assert set(_appels()) == set(_facultes())


@pytest.mark.parametrize("chemin", sorted(_facultes()))
def test_aucune_erreur_du_sdk_ne_remonte_telle_quelle(chemin: str) -> None:
    """Ce qui s'echappe remonte jusqu'a l'ecran, et pire, jusqu'au navigateur.

    Le Sage repond `f"{type(exc).__name__}: {exc}"` sur toute exception
    imprevue : une exception du SDK qui traverse une faculte finit en clair
    dans un corps JSON. Le texte brut d'une exception du SDK peut porter
    l'entete d'authentification selon les versions.

    Verifie sur l'acte, pas sur la forme : le test precedent lit le code, ici
    on fait echouer le SDK pour de vrai et on regarde ce qui sort.
    """
    from singular.analyse import AnalyseIndisponible, _sdk

    anthropic = _sdk()
    fuite = "sk-ant-SENTINELLE-dans-le-texte-de-l-exception"

    class Bizarre(anthropic.AnthropicError):
        pass

    for exception in (anthropic.APIResponseValidationError.__new__(
                          anthropic.APIResponseValidationError),
                      Bizarre(fuite)):
        if isinstance(exception, anthropic.APIResponseValidationError):
            # Construite sans passer par son __init__, qui exige une reponse
            # httpx : on ne teste pas le SDK, on teste ce qui sort de chez nous.
            Exception.__init__(exception, fuite)

        with pytest.raises(AnalyseIndisponible) as leve:
            _appels()[chemin](ClientQuiEchoue(exception))

        assert "SENTINELLE" not in str(leve.value), (
            f"{chemin} laisse remonter le texte d'une exception du SDK"
        )
        assert "sk-ant" not in str(leve.value)
