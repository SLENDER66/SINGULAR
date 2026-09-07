"""La faculté qui consomme des jetons, et tout ce qu'elle n'a pas le droit de faire.

Elle est la seule partie de SINGULAR qui dépend d'une clé, d'un service et du
réseau. Trois choses doivent donc rester vraies quoi qu'il arrive, et aucune
n'est vérifiable par la lecture d'un prompt :

* coupée, elle ne casse rien -- pas de clé, pas de paquet, pas de réseau ;
* elle ne peut rien écrire : commenter n'est pas décider, et la séparation est
  structurelle, pas une consigne dans une instruction système ;
* ce qui quitte la machine est montrable avant de partir.

Aucun test ici ne touche au réseau. Un test qui appellerait le vrai service ne
testerait pas ce fichier, il testerait la météo -- et il coûterait de l'argent
à chaque exécution du CI.
"""
from __future__ import annotations

import ast
import builtins
import pathlib
import sys

import pytest

from singular.analyse import (
    MODELE_PAR_DEFAUT,
    AnalyseIndisponible,
    analyser,
    contexte_pour_analyse,
    effort_valide,
)

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "singular" / "analyse.py"

NOTICE = {
    "headline": "Notice. 1 engagement irréversible en cours.",
    "severity": "ATTENTION",
    "generated_at": "2026-09-07T12:00:00+00:00",
    "items": [
        {"severity": "ATTENTION", "title": "1 engagement irréversible en cours",
         "detail": "Rien à corriger aujourd'hui.", "action": None, "entry_ids": ["DEC-1"]},
    ],
    "report": {"decisions": 1, "hours_total": 3.0, "irreversible_open": 1,
               "gain_expected_total": 0.0, "chain_intact": True},
}


class FauxBloc:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FausseReponse:
    def __init__(self, texte: str = "Rien d'inquietant.", stop_reason: str = "end_turn") -> None:
        self.content = [FauxBloc(texte)]
        self.stop_reason = stop_reason


class FauxClient:
    """Enregistre l'appel au lieu de le faire."""

    def __init__(self, reponse: FausseReponse | None = None) -> None:
        self.appels: list[dict] = []
        self._reponse = reponse or FausseReponse()
        self.beta = self

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.appels.append(kwargs)
        return self._reponse


# --- coupée, elle ne casse rien ----------------------------------------------

def test_sans_cle_elle_se_declare_coupee_au_lieu_de_planter(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AnalyseIndisponible, match="ANTHROPIC_API_KEY"):
        analyser(NOTICE)


def test_le_module_s_importe_sans_le_paquet(monkeypatch) -> None:
    """Le cœur ne doit pas dépendre d'un paquet que Thomas n'installera pas."""
    vrai = builtins.__import__

    def sans_anthropic(nom, *args, **kwargs):
        if nom == "anthropic":
            raise ImportError("simulé")
        return vrai(nom, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sans_anthropic)
    monkeypatch.delitem(sys.modules, "anthropic", raising=False)

    with pytest.raises(AnalyseIndisponible, match="anthropic"):
        analyser(NOTICE, client=FauxClient())


def test_un_refus_du_modele_ne_devient_pas_une_reponse_vide() -> None:
    client = FauxClient(FausseReponse("", stop_reason="refusal"))
    with pytest.raises(AnalyseIndisponible, match="refuse"):
        analyser(NOTICE, client=client)


# --- elle ne peut rien écrire -------------------------------------------------

def test_elle_ne_connait_pas_le_journal() -> None:
    """Commenter n'est pas décider : la séparation est dans les imports.

    Une instruction système peut être contournée par une tournure de phrase.
    Une absence d'import, non.
    """
    arbre = ast.parse(SOURCE.read_text(encoding="utf-8"))
    importes = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes.update(a.name for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom):
            importes.add(noeud.module or "")
            importes.update(a.name for a in noeud.names)

    interdits = {"journal", "DecisionJournal", "singular.journal", ".journal",
                 "execution", "durable_execution", "capabilities"}
    assert not (importes & interdits), (
        f"« Analyse » ne doit rien pouvoir ecrire ni executer : {sorted(importes & interdits)}"
    )


def test_le_coeur_ne_connait_pas_analyse() -> None:
    """L'inverse compte autant : le Sage ne doit jamais appeler cette faculté.

    S'il l'appelait, couper la clé casserait la Notice -- exactement ce que
    `tests/test_sage_independence.py` interdit.
    """
    racine = SOURCE.parent
    fautes = []
    for fichier in [*(racine / "sage").rglob("*.py"), racine / "journal.py"]:
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            # On juge les imports, pas le texte : « analyse » est un mot
            # français courant, et il apparaît dans les phrases que le Sage
            # écrit à l'écran. Une heuristique sur la prose échouerait sur
            # celles-ci et laisserait passer un import écrit autrement.
            if isinstance(noeud, ast.ImportFrom) and "analyse" in (noeud.module or ""):
                fautes.append(f"{fichier.name}: from {noeud.module} import ...")
            elif isinstance(noeud, ast.Import):
                fautes += [f"{fichier.name}: import {a.name}"
                           for a in noeud.names if "analyse" in a.name]

    assert not fautes, (
        "le coeur deterministe importerait une faculte qui a besoin d'une cle :\n  "
        + "\n  ".join(fautes)
    )


# --- ce qui part est montrable ------------------------------------------------

def test_le_contexte_porte_les_observations_et_les_chiffres() -> None:
    texte = contexte_pour_analyse(NOTICE)

    assert "1 engagement irréversible en cours" in texte
    assert "irreversible_open" in texte
    assert "chain_intact" in texte


def test_le_contexte_est_exactement_ce_qui_est_envoye() -> None:
    """« Voici ce qui partira » doit être la même chaîne que ce qui part.

    Deux constructions séparées divergeraient, et l'aperçu deviendrait une
    promesse invérifiable -- le défaut que ce dépôt a déjà payé ailleurs.
    """
    client = FauxClient()
    analyser(NOTICE, client=client)

    envoye = client.appels[0]["messages"][0]["content"]
    assert envoye == contexte_pour_analyse(NOTICE)


def test_l_appel_porte_le_modele_et_le_repli(monkeypatch) -> None:
    client = FauxClient()
    analyser(NOTICE, client=client)

    appel = client.appels[0]
    assert appel["model"] == MODELE_PAR_DEFAUT
    assert appel["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in appel["betas"]
    assert appel["max_tokens"] <= 4000, "la sortie est courte : plafonner est une decision de cout"


def test_un_modele_choisi_est_respecte() -> None:
    client = FauxClient()
    analyser(NOTICE, modele="claude-sonnet-5", client=client)
    assert client.appels[0]["model"] == "claude-sonnet-5"


def test_la_reponse_est_rendue_telle_quelle() -> None:
    client = FauxClient(FausseReponse("  Trois phrases.  "))
    assert analyser(NOTICE, client=client) == "Trois phrases."


# --- le contrat avec le SDK, verifie hors ligne -------------------------------
#
# Le premier vrai appel sera celui de Thomas, sur ses 5 dollars. Rien ici ne
# peut prouver que le service repondra, mais tout ce qui est verifiable sans
# reseau doit l'etre : un parametre disparu ou une valeur hors du Literal
# revient en 400 illisible, apres avoir coute une requete.

def test_le_sdk_accepte_tous_les_parametres_envoyes() -> None:
    """Une montée de version du SDK ne doit pas se découvrir sur sa facture."""
    inspect = pytest.importorskip("inspect")
    messages = pytest.importorskip("anthropic.resources.beta.messages.messages")

    signature = inspect.signature(messages.Messages.create)
    envoyes = {"model", "max_tokens", "system", "output_config",
               "betas", "fallbacks", "messages"}

    manquants = sorted(envoyes - set(signature.parameters))
    assert not manquants, (
        f"le SDK installe n'accepte plus : {manquants}. "
        "Corrige analyse.py avant que l'appel parte."
    )


def test_l_effort_configure_est_une_valeur_que_l_api_accepte() -> None:
    """`SINGULAR_ANALYSE_EFFORT=moyen` est le réflexe français, et c'est un 400."""
    typing_ = pytest.importorskip("typing")
    module = pytest.importorskip("anthropic.types.beta.beta_output_config_param")

    from singular.analyse import EFFORT, EFFORTS

    permis = typing_.get_type_hints(module.BetaOutputConfigParam)["effort"]
    literaux = set(typing_.get_args(typing_.get_args(permis)[0]))

    assert set(EFFORTS) == literaux, "EFFORTS a divergé de ce que le SDK autorise"
    assert EFFORT in literaux


def test_le_repli_par_defaut_est_une_valeur_que_l_api_accepte() -> None:
    typing_ = pytest.importorskip("typing")
    module = pytest.importorskip("anthropic.types.beta.beta_fallbacks_param")

    literal = next(a for a in typing_.get_args(module.BetaFallbacksParam)
                   if typing_.get_origin(a) is typing_.Literal)
    assert "default" in typing_.get_args(literal)


@pytest.mark.parametrize("mauvais", ["moyen", "MEDIUM", "", "tres_haut"])
def test_un_effort_mal_ecrit_retombe_sur_medium(monkeypatch, mauvais: str) -> None:
    """Silencieusement, plutôt que de faire échouer la commande sur une typo.

    Vérifié sur la fonction, plus par `importlib.reload`. Recharger ce module
    recrée `AnalyseIndisponible` : `offres` et `parle`, qui avaient importé
    l'ancienne classe, cessaient d'être rattrapés par un
    `except AnalyseIndisponible` fraîchement importé. Deux tests d'une autre
    suite tombaient, selon l'ordre d'exécution, sur une faute qui n'était pas
    la leur.
    """
    monkeypatch.setenv("SINGULAR_ANALYSE_EFFORT", mauvais)
    assert effort_valide("SINGULAR_ANALYSE_EFFORT") == "medium"


@pytest.mark.parametrize("bon", ["low", "high", "xhigh", "max"])
def test_un_effort_valide_est_respecte(monkeypatch, bon: str) -> None:
    """L'autre sens : un repli qui replierait toujours ne serait pas un repli."""
    monkeypatch.setenv("SINGULAR_ANALYSE_EFFORT", bon)
    assert effort_valide("SINGULAR_ANALYSE_EFFORT") == bon


def test_une_variable_absente_vaut_medium(monkeypatch) -> None:
    monkeypatch.delenv("SINGULAR_ANALYSE_EFFORT", raising=False)
    assert effort_valide("SINGULAR_ANALYSE_EFFORT") == "medium"


# --- la cle ne doit apparaitre nulle part -------------------------------------

# La verification de forme -- aucun message d'erreur ne peut interpoler la cle
# ni le texte brut d'une exception du SDK -- vivait ici, pour ce seul fichier.
# `offres` puis `parle` sont nes sans en heriter. Elle est desormais dans
# tests/test_facultes_sans_fuite.py, ou elle trouve elle-meme les facultes
# concernees au lieu d'en nommer une.


def test_la_cle_n_est_jamais_dans_le_contexte_envoye(monkeypatch) -> None:
    """Ceinture et bretelles : ce qui part ne contient que la Notice."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SENTINELLE")
    client = FauxClient()
    analyser(NOTICE, client=client)

    envoye = repr(client.appels[0])
    assert "SENTINELLE" not in envoye
    assert "sk-ant" not in envoye
