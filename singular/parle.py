"""Une conversation avec Claude qui n'oublie pas, parce que le journal est là.

C'est la difference exacte entre parler a Claude dans son application et
parler a SINGULAR. Le modele est le meme -- Opus 5, la meme cle. Ce qui change
est ce qu'il sait en entrant : l'application repart de zero a chaque fois,
ici le rapport du jour et le fil de la conversation precedente sont deja la.

Ce que ce module ne fait pas, et c'est structurel : il n'ecrit rien dans le
journal. Il lit la Notice, il discute, il conseille. Enregistrer une decision
reste un geste de Thomas -- `add` -- parce que penser n'est pas decider.
`tests/test_parle.py` le verifie sur les imports.

Le cout est la contrainte de conception. Une conversation renvoie tout son
historique a chaque tour : sans precaution, le dixieme tour coute dix fois le
premier, sur un budget de cinq dollars. Trois reponses a ca, dans l'ordre
d'importance : le prefixe stable est mis en cache, le fil est borne, et chaque
tour affiche ce qu'il a consomme. On ne corrige pas ce qu'on ne voit pas.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .analyse import EFFORTS, AnalyseIndisponible, _sdk
from .analyse import INSTRUCTION as INSTRUCTION_ANALYSE

#: Le fil, a cote du journal : une seule chose a sauvegarder.
FICHIER = Path.home() / ".singular" / "conversation.json"

MODELE_PAR_DEFAUT = os.environ.get("SINGULAR_PARLE_MODELE", "claude-opus-5")

EFFORT = os.environ.get("SINGULAR_PARLE_EFFORT", "medium")
if EFFORT not in EFFORTS:
    EFFORT = "medium"

#: Au-dela, le fil coute plus qu'il n'apporte : les vieux tours sont rarement
#: ce qui manque, et ils sont renvoyes en entier a chaque question.
TOURS_GARDES = 20

JETONS_MAX = 2000

INSTRUCTION = INSTRUCTION_ANALYSE + """

Tu es maintenant dans une conversation, pas dans un rapport. Reponds a ce
qu'il demande, brievement. S'il te demande d'enregistrer une decision, dis-lui
la commande -- `python -m singular add` -- au lieu de pretendre l'avoir fait :
tu n'as aucun moyen d'ecrire dans son journal, et faire semblant serait le
pire service possible.
"""


class Conversation:
    """Le fil, sur le disque. Rien de plus qu'une liste de tours."""

    def __init__(self, chemin: Path | str = FICHIER) -> None:
        self.chemin = Path(chemin)
        self.tours: list[dict[str, str]] = []
        self._charger()

    def _charger(self) -> None:
        if not self.chemin.exists():
            return
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Un fil illisible n'est pas une raison de perdre la parole : on
            # repart a vide plutot que d'echouer. Le journal, lui, refuserait --
            # mais lui porte des faits, pas une discussion.
            return
        tours = donnees.get("tours", [])
        self.tours = [t for t in tours
                      if isinstance(t, dict) and t.get("role") in ("user", "assistant")]

    def ajouter(self, role: str, texte: str) -> None:
        self.tours.append({"role": role, "content": texte})
        del self.tours[:-TOURS_GARDES * 2]

    def sauver(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.chemin.write_text(
            json.dumps({"tours": self.tours, "maj": datetime.now(UTC).isoformat()},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def oublier(self) -> None:
        self.tours = []
        self.chemin.unlink(missing_ok=True)


def _systeme(contexte: str) -> list[dict[str, Any]]:
    """L'instruction et le rapport du jour, en un bloc mis en cache.

    C'est la partie qui ne bouge pas d'un tour a l'autre. La mettre en cache
    la fait payer une fois au lieu d'a chaque question -- et le cache est un
    prefixe : le moindre octet qui change avant ce point le perd. D'ou un seul
    bloc, et la question de l'utilisateur apres, jamais dedans.
    """
    return [{
        "type": "text",
        "text": f"{INSTRUCTION}\n\nSon rapport du jour :\n\n{contexte}",
        "cache_control": {"type": "ephemeral"},
    }]


def repondre(
    question: str,
    contexte: str,
    conversation: Conversation,
    *,
    modele: str | None = None,
    client: Any = None,
) -> tuple[str, dict[str, int]]:
    """Un tour de conversation. Rend la reponse et ce qu'elle a consomme."""
    if client is None:
        cle = os.environ.get("ANTHROPIC_API_KEY")
        if not cle:
            raise AnalyseIndisponible(
                "aucune cle dans ANTHROPIC_API_KEY. Le reste de SINGULAR marche sans."
            )
        client = _sdk().Anthropic(api_key=cle)

    anthropic = _sdk()
    messages = [*conversation.tours, {"role": "user", "content": question}]
    try:
        reponse = client.beta.messages.create(
            model=modele or MODELE_PAR_DEFAUT,
            max_tokens=JETONS_MAX,
            system=_systeme(contexte),
            output_config={"effort": EFFORT},
            # Meme repli cote serveur qu'`analyse`, et pour une raison plus
            # forte ici : un tour perdu au milieu d'une conversation coute le
            # fil, pas seulement une commande a relancer.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=messages,
        )
    except anthropic.AuthenticationError:
        raise AnalyseIndisponible("la cle est refusee. Verifie ANTHROPIC_API_KEY.") from None
    except anthropic.RateLimitError:
        raise AnalyseIndisponible("trop de requetes. Reessaie dans une minute.") from None
    except anthropic.APIConnectionError:
        raise AnalyseIndisponible("pas de reseau. Le reste de SINGULAR marche sans.") from None
    except anthropic.APIStatusError as erreur:
        raise AnalyseIndisponible(f"le service a repondu {erreur.status_code}.") from None

    if reponse.stop_reason == "refusal":
        raise AnalyseIndisponible("le modele a refuse de repondre.")

    texte = "\n".join(b.text for b in reponse.content if b.type == "text").strip()
    conversation.ajouter("user", question)
    conversation.ajouter("assistant", texte)
    return texte, _consommation(reponse)


def _consommation(reponse: Any) -> dict[str, int]:
    """Ce que le tour a coute, en jetons. Affiche, parce qu'on ne corrige pas
    ce qu'on ne voit pas -- et parce que le budget est de cinq dollars."""
    usage = getattr(reponse, "usage", None)
    return {
        "entree": getattr(usage, "input_tokens", 0) or 0,
        "sortie": getattr(usage, "output_tokens", 0) or 0,
        "cache_lu": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_ecrit": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


__all__ = ["FICHIER", "JETONS_MAX", "MODELE_PAR_DEFAUT", "TOURS_GARDES",
           "Conversation", "repondre"]
