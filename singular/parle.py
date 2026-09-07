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

from .analyse import INSTRUCTION as INSTRUCTION_ANALYSE
from .analyse import AnalyseIndisponible, _sdk, effort_valide

#: Le fil, a cote du journal : une seule chose a sauvegarder.
FICHIER = Path.home() / ".singular" / "conversation.json"

#: Le compteur du jour, a cote du fil.
FICHIER_QUOTA = Path.home() / ".singular" / "parle_quota.json"

#: Ses tarifs, qu'il ecrit lui-meme. Ce depot n'en connait aucun.
FICHIER_TARIFS = Path.home() / ".singular" / "tarifs.json"

#: Sonnet, pas Opus, et c'est la seule faculte ou le defaut change.
#:
#: `analyse` et `offres` sont des coups uniques : une fois par jour, une fois
#: par semaine. Une conversation, c'est vingt appels dans la soiree, chacun
#: portant tout ce qui precede. Sur un credit de cinq dollars, le choix du
#: modele decide si la conversation dure une semaine ou un apres-midi -- et
#: Opus coute plus cher que Sonnet.
#:
#: Ce n'est pas un rabais sur ce qu'il a demande : Sonnet 5 est un vrai
#: modele Claude, le meme SDK, la meme cle. Et le retour se fait par une
#: variable : `SINGULAR_PARLE_MODELE=claude-opus-5`.
MODELE_PAR_DEFAUT = os.environ.get("SINGULAR_PARLE_MODELE", "claude-sonnet-5")

EFFORT = effort_valide("SINGULAR_PARLE_EFFORT")

#: Au-dela, le fil coute plus qu'il n'apporte : les vieux tours sont rarement
#: ce qui manque, et ils sont renvoyes en entier a chaque question.
TOURS_GARDES = 20

JETONS_MAX = 2000

#: Le plafond quotidien, quand la conversation est ouverte depuis le telephone.
#: Un bouton se tapote ; une commande se tape. Ce n'est pas la meme retenue.
#:
#: Il etait a vingt, et vingt tours c'est une seule vraie conversation : le
#: plafond devenait ce qui interrompt, alors qu'il devait etre ce qui protege.
#: « Converser en continu quand je le souhaite » et « avec un plafond » ne se
#: contredisent que si le plafond compte la mauvaise chose.
#:
#: Il compte donc des tours assez large pour ne pas se faire sentir, et la
#: vraie garde est ailleurs : le credit restant, calcule avec ses tarifs a lui,
#: qui refuse quand il n'y a plus d'argent. Un garde-fou contre l'emballement
#: -- une poche, un enfant, une soiree distraite -- pas contre l'usage.
PLAFOND_PAR_JOUR = 60


def _aujourdhui() -> str:
    """La date locale. `date.today()` dit la meme chose ; ruff la refuse parce
    qu'elle est muette sur le fuseau. Ici le fuseau est le sien, exprès."""
    return datetime.now().astimezone().date().isoformat()


class PlafondAtteint(Exception):
    """Le nombre de tours du jour est epuise. Demain, ou depuis le clavier."""


class Quota:
    """Le compteur du jour et la depense de toujours, sur le disque.

    Sur le disque et pas en memoire, sinon redemarrer le serveur remettrait le
    compteur a zero : un plafond qu'un redemarrage efface n'est pas un plafond.

    La date est locale, pas UTC : « aujourd'hui » est sa journee a lui, celle
    ou il regarde son telephone, pas celle du meridien de Greenwich.

    Le total des jetons, lui, ne se remet jamais a zero. C'est la seule chose
    qui repond a la question qui compte quand on a achete cinq dollars de
    credit : est-ce que je suis en train de les bruler ?
    """

    def __init__(self, chemin: Path | str | None = None, *, plafond: int | None = None) -> None:
        self.chemin = Path(chemin) if chemin else FICHIER_QUOTA
        self.plafond = PLAFOND_PAR_JOUR if plafond is None else plafond

    def _lire(self) -> dict[str, Any]:
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # L'ecriture est atomique (voir `_ecrire`), donc un fichier illisible
            # n'est pas une ecriture interrompue : c'est un premier lancement, ou
            # quelqu'un qui a efface le compteur sur sa propre machine. Repartir
            # de zero est la bonne lecture, et le refus serait une panne.
            return {}
        return donnees if isinstance(donnees, dict) else {}

    def _ecrire(self, donnees: dict[str, Any]) -> None:
        # Atomique : un plafond qui se corrompt en tombant serait un plafond
        # qu'une coupure de courant remet a zero.
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        provisoire = self.chemin.with_suffix(".tmp")
        provisoire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        provisoire.replace(self.chemin)

    @staticmethod
    def _tours_du_jour(donnees: dict[str, Any], jour: str) -> int:
        if str(donnees.get("jour", "")) != jour:
            return 0
        try:
            return max(0, int(donnees.get("tours", 0)))
        except (TypeError, ValueError):
            return 0

    def restants(self, *, aujourdhui: str | None = None) -> int:
        jour = aujourdhui or _aujourdhui()
        return max(0, self.plafond - self._tours_du_jour(self._lire(), jour))

    def depenses(self) -> dict[str, dict[str, int]]:
        """Les jetons consommes depuis toujours, modele par modele.

        Modele par modele parce que leurs tarifs different : un total unique
        melangerait des jetons qui ne coutent pas le meme prix, et donnerait
        un chiffre qu'on ne peut convertir en rien.
        """
        brut = self._lire().get("jetons", {})
        if not isinstance(brut, dict):
            return {}
        propre: dict[str, dict[str, int]] = {}
        for modele, compte in brut.items():
            if not isinstance(compte, dict):
                continue
            propre[str(modele)] = {
                poste: int(compte.get(poste, 0) or 0)
                for poste in ("entree", "sortie", "cache_lu", "cache_ecrit")
            }
        return propre

    @staticmethod
    def _cumuler(jetons: dict[str, dict[str, int]], cout: dict[str, int] | None,
                 modele: str) -> dict[str, dict[str, int]]:
        if not (cout and modele):
            return jetons
        compte = jetons.setdefault(modele, dict.fromkeys(
            ("entree", "sortie", "cache_lu", "cache_ecrit"), 0))
        for poste, valeur in cout.items():
            if poste in compte:
                compte[poste] += int(valeur or 0)
        return jetons

    def ajouter_depense(self, *, cout: dict[str, int], modele: str) -> None:
        """Compter une depense sans entamer le plafond du jour.

        C'est ce que fait le clavier. Les deux surfaces ecrivent le meme
        fichier, et faire passer les tours du clavier par `consommer` revenait
        a leur faire manger le plafond du telephone : trois questions au PC, et
        le telephone n'en avait plus que cinquante-sept -- alors que la
        documentation promet au clavier de ne pas etre plafonne.

        La depense, elle, se compte partout : c'est le credit achete, et il ne
        sait pas d'ou vient la question.
        """
        donnees = self._lire()
        donnees["jetons"] = self._cumuler(self.depenses(), cout, modele)
        self._ecrire(donnees)

    def consommer(self, *, cout: dict[str, int] | None = None, modele: str = "",
                  aujourdhui: str | None = None) -> int:
        """Compte un tour, ajoute sa depense, et rend ce qu'il reste du jour.

        Leve si le jour est fini. Un seul ecrit pour les deux : le tour et sa
        facture sont le meme evenement, et les separer laisserait une fenetre
        ou l'un est compte sans l'autre.
        """
        jour = aujourdhui or _aujourdhui()
        donnees = self._lire()
        deja = self._tours_du_jour(donnees, jour)
        if deja >= self.plafond:
            raise PlafondAtteint(
                f"{self.plafond} reponses aujourd'hui, c'est le plafond. "
                "Demain, ou depuis le clavier avec `python -m singular parle`."
            )

        jetons = self._cumuler(self.depenses(), cout, modele)
        self._ecrire({**donnees, "jour": jour, "tours": deja + 1, "jetons": jetons})
        return self.plafond - (deja + 1)


class Tarifs:
    """Ce que ses jetons lui coutent -- ses chiffres, pas les miens.

    SINGULAR ne connait aucun prix, et c'est deliberé. Les tarifs changent, ce
    depot ne se met pas a jour tout seul, et un chiffre faux ici serait pire
    qu'aucun chiffre : il servirait a decider quand s'arreter. La seule verite
    est sur console.anthropic.com, et sur sa facture.

    Il ecrit donc les siens dans `~/.singular/tarifs.json`. Tant qu'il ne l'a
    pas fait, la conversation compte les jetons et ne parle jamais d'argent.
    """

    #: En dollars par million de jetons, comme la console les affiche.
    POSTES = ("entree", "sortie", "cache_lu", "cache_ecrit")

    def __init__(self, chemin: Path | str | None = None) -> None:
        self.chemin = Path(chemin) if chemin else FICHIER_TARIFS
        self.credit: float | None = None
        self.modeles: dict[str, dict[str, float]] = {}
        self._charger()

    def _charger(self) -> None:
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(donnees, dict):
            return
        credit = donnees.get("credit_usd")
        if isinstance(credit, int | float) and credit >= 0:
            self.credit = float(credit)
        modeles = donnees.get("modeles", {})
        if not isinstance(modeles, dict):
            return
        for nom, prix in modeles.items():
            if not isinstance(prix, dict):
                continue
            retenu = {poste: float(prix[poste]) for poste in self.POSTES
                      if isinstance(prix.get(poste), int | float)}
            if retenu:
                self.modeles[str(nom)] = retenu

    def connait(self, modele: str) -> bool:
        return modele in self.modeles

    def cout_usd(self, depenses: dict[str, dict[str, int]]) -> float | None:
        """Ce que ces jetons ont coute, ou None si un modele n'a pas de tarif.

        None plutot qu'un total partiel : un chiffre qui oublie silencieusement
        un modele est un chiffre faux, et il servirait a decider quand
        s'arreter.
        """
        if not self.modeles:
            # Aucun tarif donne : « 0,00 $ » serait vrai et trompeur -- il
            # laisserait croire que ce depot connait les prix, alors qu'il
            # attend les siens.
            return None
        if not depenses:
            return 0.0
        total = 0.0
        for modele, compte in depenses.items():
            prix = self.modeles.get(modele)
            if prix is None:
                return None
            for poste, jetons in compte.items():
                total += jetons * prix.get(poste, 0.0) / 1_000_000
        return total

    def restant_usd(self, depenses: dict[str, dict[str, int]]) -> float | None:
        """Ce qu'il reste du credit qu'il a achete, s'il l'a ecrit."""
        depense = self.cout_usd(depenses)
        if self.credit is None or depense is None:
            return None
        return max(0.0, self.credit - depense)


def etat_de_la_faculte() -> tuple[bool, str]:
    """La conversation est-elle allumee, et sinon pourquoi -- en une phrase.

    Existe pour etre affichee au demarrage du Sage. La cle se met dans la
    fenetre ou l'on lance le serveur, avant de le lancer, et la commande n'est
    pas la meme en `cmd` et en PowerShell : l'oubli est silencieux, et il ne se
    decouvre qu'une fois le telephone en main, loin du clavier.

    Le Sage ne peut pas ecrire ce diagnostic lui-meme : `test_sage_independence`
    lui interdit jusqu'au nom d'une variable de cle. La phrase vient donc d'ici,
    ou elle a le droit d'exister.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, ("conversation coupee   aucune cle dans ANTHROPIC_API_KEY "
                       "-- le bouton le dira aussi")
    try:
        _sdk()
    except AnalyseIndisponible as coupee:
        return False, f"conversation coupee   {coupee}"
    return True, f"conversation allumee  {MODELE_PAR_DEFAUT}, {PLAFOND_PAR_JOUR} reponses par jour"


def bilan(quota: Quota | None = None, tarifs: Tarifs | None = None) -> dict[str, Any]:
    """Ce que la conversation a coute, pret a afficher.

    Une seule fonction pour les deux surfaces -- le clavier et le telephone.
    La meme verite ecrite deux fois finit par diverger, et celle-ci est un
    chiffre d'argent : la divergence ne se verrait qu'a la facture.

    `usd` vaut None quand il n'a pas ecrit ses tarifs, ou quand un modele
    utilise n'y figure pas. None, jamais un total partiel : un chiffre qui
    oublie un modele sert quand meme a decider quand s'arreter.
    """
    quota = quota or Quota()
    tarifs = tarifs or Tarifs()
    depenses = quota.depenses()
    jetons = {poste: sum(compte.get(poste, 0) for compte in depenses.values())
              for poste in Tarifs.POSTES}
    return {
        "jetons": jetons,
        "modeles": sorted(depenses),
        "usd": tarifs.cout_usd(depenses),
        "credit_usd": tarifs.credit,
        "restant_usd": tarifs.restant_usd(depenses),
        "tarifs": str(tarifs.chemin),
    }


def phrase_de_bilan(bilan_: dict[str, Any]) -> str:
    """Le bilan en une ligne, la meme au clavier et sur le telephone.

    Sans tarifs, elle dit des jetons et ou trouver les prix. Avec, elle dit
    des dollars -- et il n'y a que ca qui reponde a « est-ce que je brule mon
    credit ? ».
    """
    jetons = bilan_["jetons"]
    envoyes = jetons["entree"] + jetons["cache_lu"] + jetons["cache_ecrit"]
    if bilan_["usd"] is None:
        return (f"{envoyes} jetons envoyes, {jetons['sortie']} rendus depuis le debut. "
                f"Pour voir des dollars, ecris tes tarifs dans {bilan_['tarifs']}.")
    if bilan_["restant_usd"] is None:
        return f"environ {bilan_['usd']:.2f} $ depenses depuis le debut."
    return (f"environ {bilan_['usd']:.2f} $ depenses, "
            f"il te reste environ {bilan_['restant_usd']:.2f} $ sur "
            f"{bilan_['credit_usd']:.2f} $.")


#: Ce qu'il colle dans `~/.singular/tarifs.json`, avec ses chiffres a lui.
MODELE_DE_TARIFS = """{
  "credit_usd": 5.0,
  "modeles": {
    "claude-sonnet-5": {
      "entree": 0.0,
      "sortie": 0.0,
      "cache_lu": 0.0,
      "cache_ecrit": 0.0
    }
  }
}
"""


INSTRUCTION = INSTRUCTION_ANALYSE + """

Tu es maintenant dans une conversation, pas dans un rapport. Reponds a ce
qu'il demande, brievement. S'il te demande d'enregistrer une decision, dis-lui
la commande -- `python -m singular add` -- au lieu de pretendre l'avoir fait :
tu n'as aucun moyen d'ecrire dans son journal, et faire semblant serait le
pire service possible.
"""


class Conversation:
    """Le fil, sur le disque. Rien de plus qu'une liste de tours."""

    def __init__(self, chemin: Path | str | None = None) -> None:
        # Resolu a l'appel, pas fige dans la signature : un defaut evalue a
        # l'import rendrait le chemin impossible a deplacer -- pour un test,
        # pour un second profil, pour un disque externe.
        self.chemin = Path(chemin) if chemin else FICHIER
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


def _messages(conversation: Conversation, question: str) -> list[dict[str, Any]]:
    """Le fil, avec le cache pose sur ce qui ne bougera plus.

    C'est ce qui rend une conversation continue tenable. Sans ca, le fil
    entier est refacture au plein tarif a chaque tour : le vingtieme coute
    vingt fois le premier, et cinq dollars ne durent pas la soiree.

    Le cache est un prefixe. On le pose donc sur le dernier tour deja
    enregistre -- tout ce qui precede la nouvelle question -- de sorte que le
    tour suivant relise ce bloc au lieu de le repayer. La question du moment
    reste en clair apres la marque : elle change a chaque fois, et la mettre
    dedans invaliderait le prefixe qu'on essaie de garder.

    Les tours sont stockes en texte simple ; la marque est posee ici, au
    moment de l'envoi. Le fichier sur le disque reste lisible a l'oeil.
    """
    messages: list[dict[str, Any]] = [dict(tour) for tour in conversation.tours]
    if messages:
        dernier = messages[-1]
        dernier["content"] = [{
            "type": "text",
            "text": dernier["content"],
            "cache_control": {"type": "ephemeral"},
        }]
    messages.append({"role": "user", "content": question})
    return messages


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
    messages = _messages(conversation, question)
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
    except anthropic.AnthropicError:
        # Le filet. Les quatre familles ci-dessus ne couvrent pas tout l'arbre
        # du SDK, et ce qui s'echappe remonte tel quel jusqu'a l'ecran :
        # l'explication est dans `analyse.py`, au meme endroit.
        raise AnalyseIndisponible(
            "le service a echoue d'une facon imprevue. Rien n'a ete ecrit."
        ) from None

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


__all__ = ["FICHIER", "FICHIER_QUOTA", "FICHIER_TARIFS", "JETONS_MAX",
           "MODELE_DE_TARIFS", "MODELE_PAR_DEFAUT", "PLAFOND_PAR_JOUR", "TOURS_GARDES",
           "Conversation", "PlafondAtteint", "Quota", "Tarifs",
           "bilan", "etat_de_la_faculte", "phrase_de_bilan", "repondre"]
