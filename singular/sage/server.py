"""Le serveur du Sage : une app web, installable sur l'écran d'accueil.

Pourquoi une app web et pas une app iOS : une app native demande un Mac, Xcode
et un compte développeur Apple. Une PWA ajoutée à l'écran d'accueil depuis
Safari donne une icône, le plein écran et, depuis iOS 16.4, les notifications --
sans rien de tout ça.

Pourquoi la bibliothèque standard et pas un framework : ce serveur doit démarrer
sur une machine où rien n'est installé, avec une seule commande et zéro
`pip install`. C'était un PC Windows jusqu'au 10 septembre 2026, c'est un Mac
depuis, et c'est aussi a-Shell sur l'iPhone -- la contrainte n'a pas bougé en
changeant de machine, et c'est bien pour ça qu'elle est tenue ainsi. Un outil
qui demande une installation avant de servir est un outil qu'on n'ouvre pas.

Ce serveur lit et écrit le journal. Il n'importe rien de la frontière
d'exécution -- un test le vérifie -- de sorte qu'aucune requête HTTP ne peut
déclencher d'action sur le monde. Le Sage observe et conseille ; toi seul
décides.
"""
from __future__ import annotations

import errno
import importlib
import json
import sqlite3
import re
import secrets
import ipaddress
import socket
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus, urlsplit

from ..fichiers import ecrire_atomique
from ..collecte import collecter
from ..journal import DEFAULT_PATH, DecisionJournal, Reversibility, Status, Tier
from ..saisie import CONFLIT_PAGE, introuvable, verifie_decision
from .icon import render_icon
from .notice import build_notice

WEB_ROOT = Path(__file__).parent / "web"
TOKEN_PATH = DEFAULT_PATH.parent / "sage_token"

#: Un corps de requête plus gros que ça n'est pas une décision de journal.
MAX_BODY = 64 * 1024

#: Une question plus longue que ça n'est plus une question, c'est un fichier --
#: et elle part vers un service qui facture ce qu'on lui envoie.
QUESTION_MAX = 2000

#: Les seules adresses qui n'ont pas besoin du jeton : elles ne peuvent venir
#: que de la machine elle-même.
LOOPBACK = frozenset({"127.0.0.1", "::1"})

#: Le seul type de corps que l'API accepte en écriture.
#:
#: Ce n'est pas du pédantisme : un navigateur n'envoie une requête d'une page
#: vers une autre origine sans autorisation préalable que si le type est
#: `text/plain`, un formulaire ou du multipart. Exiger du JSON force donc le
#: navigateur à demander la permission d'abord -- permission que ce serveur ne
#: donne jamais, puisqu'il n'annonce aucune règle de partage entre origines.
JSON_BODY = "application/json"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

ENTRY_ID = re.compile(r"^DEC-[0-9a-f]{8}$")


class SageError(Exception):
    """Une requête refusée, avec le code que le client doit voir."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def read_token(path: Path = TOKEN_PATH) -> str:
    """Le jeton d'accès, créé une fois et gardé sur le disque.

    Ouvrir le journal au réseau local, c'est l'ouvrir à tout ce qui est sur le
    wifi. Le jeton coûte un paramètre dans l'adresse la première fois -- l'app
    le garde ensuite -- et il évite qu'un journal personnel soit lisible par
    n'importe quel appareil de la maison.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            _restreindre(path)
            return existing
    token = secrets.token_urlsafe(18)
    # Les droits sont poses a la creation du fichier provisoire, pas apres
    # l'ecriture : le jeton etait ecrit en clair puis resserre a 0600, et entre
    # les deux il etait lisible par tout le monde.
    ecrire_atomique(path, token, permissions=0o600)
    _restreindre(path)
    return token


def _restreindre(path: Path) -> None:
    """Le jeton n'est lisible que par son propriétaire.

    Il était créé en 0644, comme tout fichier écrit sans le dire. Sur le PC
    Windows d'un utilisateur unique -- la machine principale jusqu'au
    10 septembre 2026 -- ça ne changeait rien, et c'est pour ça que personne ne
    l'avait vu. Le cœur tourne désormais sur un Mac, sur le téléphone, et sur
    des machines multi-utilisateurs où « lisible par tout le monde » veut dire
    ce qu'il dit : la clé du journal personnel, en clair, à côté de lui.

    Un fichier déjà écrit est resserré au passage : sinon la correction ne
    protégerait que les installations neuves, c'est-à-dire personne.

    Sur macOS le mode est honoré tel quel -- vérifié, le fichier sort en 0600.
    Ailleurs il peut ne pas l'être : Windows ne sait poser que le bit lecture
    seule. L'échec n'est donc pas une panne et ne doit pas empêcher le Sage de
    démarrer -- un journal qu'on ne peut pas ouvrir serait pire que le défaut
    qu'on corrige.
    """
    try:
        path.chmod(0o600)
    except OSError:
        pass


def local_address() -> str:
    """L'adresse de cette machine sur le réseau local, pour l'afficher."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 53))  # TEST-NET-1: routé nulle part, jamais joint
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _tier(raw: Any) -> Tier:
    try:
        return Tier(str(raw).strip().upper())
    except ValueError:
        raise SageError(HTTPStatus.BAD_REQUEST, f"rang inconnu : {raw}") from None


def _number(payload: dict[str, Any], name: str, *, cast) -> Any:
    if name not in payload:
        raise SageError(HTTPStatus.BAD_REQUEST, f"« {name} » est obligatoire")
    try:
        return cast(payload[name])
    except (TypeError, ValueError):
        raise SageError(HTTPStatus.BAD_REQUEST, f"« {name} » doit être un nombre") from None


def _gain(payload: dict[str, Any]) -> float | None:
    """Vide veut dire « non chiffré », jamais « zéro ».

    Un formulaire renvoie toujours la clé, avec une chaîne vide quand le champ
    n'a pas été rempli. La lire comme 0 inventerait un gain nul et effacerait
    exactement ce que la Notice doit reprocher : les heures engagées sur des
    décisions dont personne n'a estimé le rendement.

    La virgule est acceptée : on tape « 5000,50 » sur un clavier français, et
    faire échouer une décision pour ça serait la meilleure façon de ne plus en
    enregistrer.
    """
    brut = payload.get("expected_gain_eur")
    if brut is None:
        return None
    # Toutes les espaces, pas seulement la nôtre : un clavier iOS insère une
    # espace fine insécable comme séparateur de milliers, invisible à l'oeil et
    # fatale à float(). Elle est retirée par ce qu'elle est, et non écrite en
    # toutes lettres ici -- la console Windows ne sait pas l'afficher, et
    # tests/test_windows_console.py refuse ce caractère dans ce fichier.
    texte = "".join(c for c in str(brut) if not c.isspace()).replace(",", ".")
    if not texte:
        return None
    try:
        return float(texte)
    except (TypeError, ValueError):
        raise SageError(HTTPStatus.BAD_REQUEST, "« gain attendu » doit être un nombre") from None


def _reversibility(payload: dict[str, Any]) -> Reversibility | None:
    """Non renseignée est une réponse valable : « je ne sais pas encore »."""
    brut = payload.get("reversibility")
    if brut is None:
        return None
    texte = str(brut).strip().upper()
    if not texte:
        return None
    try:
        return Reversibility(texte)
    except ValueError:
        raise SageError(HTTPStatus.BAD_REQUEST, f"réversibilité inconnue : {brut}") from None


def _text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name, "")).strip()
    if not value:
        raise SageError(HTTPStatus.BAD_REQUEST, f"« {name} » est obligatoire")
    return value


def _entry_as_dict(entry: Any) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "action": entry.action,
        "predicted": entry.predicted,
        "probability": entry.probability,
        "tier": entry.tier.value,
        "tier_label": entry.tier.label,
        "cost_hours": entry.cost_hours,
        "horizon_days": entry.horizon_days,
        "created_at": entry.created_at,
        "due_at": entry.due_at,
        "status": entry.status.value,
        "overdue_days": entry.overdue_days() if entry.is_open else 0,
        # « échue » et « en retard » ne sont pas la même chose : le jour dit,
        # le retard vaut zéro et la décision demande pourtant un verdict.
        # La liste marquait donc en gris la carte que le rapport mettait en tête.
        "is_due": entry.is_due() if entry.is_open else False,
        "lesson": entry.lesson or "",
        "brier_score": entry.brier_score,
        "expected_gain_eur": entry.expected_gain_eur,
        "reversibility": None if entry.reversibility is None else entry.reversibility.value,
        "reversibility_label": None if entry.reversibility is None else entry.reversibility.label,
    }


def _faculte_offres(*noms: str) -> tuple[Any, ...]:
    """La recherche d'offres, si elle est là — sinon un refus qui se lit.

    L'import est tardif, et il est protégé. Tardif : le Sage doit démarrer,
    afficher la Notice et enregistrer une décision sur une machine où la
    faculté a été retirée. Protégé : sans ça, l'absence remonterait en
    ImportError jusqu'à l'écran du téléphone, sous forme de 500, et une
    faculté coupée ressemblerait à une panne de l'app.

    `tests/test_offres.py` ne le vérifie plus sur les imports mais en coupant
    réellement le module, puis en refaisant tout le parcours gratuit.
    """
    try:
        # `importlib` et pas `from .. import offres` : le second lit l'attribut
        # deja pose sur le paquet et reussit meme quand le module a ete retire,
        # ce qui rendait la coupure intestable -- donc invérifiable, donc
        # promise plutot que tenue.
        offres = importlib.import_module("singular.offres")
    except ImportError:
        raise SageError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "la recherche d'offres n'est pas disponible sur cette installation. "
            "Le journal, la Notice et les verdicts marchent sans elle.",
        ) from None
    return tuple(getattr(offres, nom) for nom in noms)


class SageApp:
    """Le routage et la logique, sans rien qui touche à HTTP.

    Séparé du gestionnaire de requêtes pour que les tests appellent les routes
    directement : un test qui monte un vrai serveur pour vérifier une règle
    métier teste surtout le serveur.
    """

    def __init__(self, journal: DecisionJournal, *, token: str = "") -> None:
        self.journal = journal
        self.token = token
        # Un tour de conversation a la fois. Le serveur est multi-thread, un
        # bouton se tapote, et deux tours simultanes feraient trois degats :
        # deux factures pour une question, deux ecritures du fil dont la
        # seconde ecrase la premiere, et deux reponses a une conversation qui
        # n'en attend qu'une. Le verrou de l'interface evite qu'on le tente ;
        # celui-ci le rend impossible, ce qui n'est pas la meme chose.
        self._un_tour = threading.Lock()

    # --- lecture -------------------------------------------------------------

    def notice(self) -> dict[str, Any]:
        """Le rapport, plus l'endroit ou l'on a regarde.

        Un journal vide et un mauvais journal donnent exactement le meme
        ecran. Le coeur tourne sur son Mac et sur son telephone, sur deux
        fichiers qui ne se parlent pas : il peut tres bien ouvrir l'app et voir
        « Le journal est vide » parce que le serveur pointe ailleurs, pas parce
        qu'il a tout perdu. La ligne de commande le disait deja -- c'est ce que
        `_vide()` fait dans `__main__.py` -- et l'app, celle qu'il ouvre le
        matin, ne le disait pas.

        Le chemin est pose ici, en dehors de `items` et de `report` : c'est
        exactement ce que `contexte_pour_analyse` recopie, et le chemin porte
        son nom d'utilisateur. Il s'affiche chez lui, il ne part pas.
        `test_ce_qui_part.py` le verifie.
        """
        return {**build_notice(self.journal).as_dict(), "journal": str(self.journal.path)}

    def collecte(self) -> dict[str, Any]:
        """Ce que le Scout a trouvé hors du journal, tel quel.

        La route ne juge pas plus que lui : elle recopie les faits avec leur
        source et leur date. Le fichier absent n'est pas une panne -- c'est le
        cas normal tant qu'il n'a pas ouvert le suivi de candidatures sur cette
        machine, et le Scout le dit comme un fait établi.
        """
        return {"faits": [{"sujet": f.sujet, "texte": f.texte, "source": f.source,
                           "date": f.date, "verifie": f.verifie}
                          for f in collecter()]}

    def entries(self, status: str | None = None) -> dict[str, Any]:
        chosen = None
        if status:
            try:
                chosen = Status(status.upper())
            except ValueError:
                raise SageError(HTTPStatus.BAD_REQUEST, f"statut inconnu : {status}") from None
        return {
            "entries": [_entry_as_dict(entry) for entry in self.journal.entries(status=chosen)],
            "tiers": [{"value": tier.value, "label": tier.label, "rank": tier.rank} for tier in Tier],
        }

    # --- écriture ------------------------------------------------------------

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Enregistrer une decision. Les refus sont dits dans sa langue.

        Ils ne l'etaient pas : cette route laissait le journal lever, et
        renvoyait son message tel quel. Sur son telephone, taper « -100 » dans
        le champ du gain -- qui n'a aucune borne, exprès, pour que « vide »
        reste possible -- rendait `expected_gain_eur cannot be negative: a cost
        is not a gain`. Le clavier repondait deja en francais ; le formulaire
        posait ses propres bornes en HTML. Trois ecritures de la meme regle,
        dont une muette.
        """
        probabilite = _number(payload, "probability", cast=float)
        heures = _number(payload, "cost_hours", cast=float)
        jours = _number(payload, "horizon_days", cast=int)
        gain = _gain(payload)
        try:
            verifie_decision(probability=probabilite, cost_hours=heures,
                             horizon_days=jours, expected_gain_eur=gain)
        except ValueError as refus:
            raise SageError(HTTPStatus.BAD_REQUEST, str(refus)) from None
        try:
            entry = self.journal.add(
                title=_text(payload, "title"),
                action=_text(payload, "action"),
                predicted=_text(payload, "predicted"),
                probability=probabilite,
                tier=_tier(payload.get("tier", Tier.REVENUS.value)),
                cost_hours=heures,
                horizon_days=jours,
                expected_gain_eur=gain,
                reversibility=_reversibility(payload),
            )
        except ValueError as exc:
            raise SageError(HTTPStatus.BAD_REQUEST, str(exc)) from None
        return _entry_as_dict(entry)

    def resolve(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if "happened" not in payload or not isinstance(payload["happened"], bool):
            raise SageError(HTTPStatus.BAD_REQUEST, "« happened » doit valoir vrai ou faux")
        try:
            entry = self.journal.resolve(
                entry_id, happened=payload["happened"], lesson=str(payload.get("lesson", "")).strip()
            )
        except KeyError:
            raise SageError(HTTPStatus.NOT_FOUND, introuvable(entry_id)) from None
        except PermissionError:
            # `str(exc)` renvoyait « history is not editable » dans la reponse
            # JSON. L'app remplacait la phrase de son cote ; le corps, lui,
            # partait en anglais, et rien ne garantissait que le remplacement
            # survive a la prochaine reecriture du client.
            raise SageError(HTTPStatus.CONFLICT, CONFLIT_PAGE) from None
        return _entry_as_dict(entry)

    def abandon(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            entry = self.journal.abandon(entry_id, reason=_text(payload, "reason"))
        except KeyError:
            raise SageError(HTTPStatus.NOT_FOUND, introuvable(entry_id)) from None
        except PermissionError:
            raise SageError(HTTPStatus.CONFLICT, CONFLIT_PAGE) from None
        return _entry_as_dict(entry)

    # --- la conversation, quand elle est allumée ------------------------------

    def parle_etat(self) -> dict[str, Any]:
        """Le fil et ce qu'il reste de la journée. Gratuit, sans clé, sans SDK.

        Rouvrir l'app doit montrer la conversation d'hier soir : sans ça, le
        fil existe sur le disque et nulle part à l'écran.
        """
        from ..analyse import contexte_pour_analyse
        from ..parle import (
            PLAFOND_PAR_JOUR,
            Conversation,
            Quota,
            apercu,
            bilan,
            phrase_de_bilan,
        )

        fil = Conversation()
        compte = bilan(Quota())
        return {
            # Ce qui partirait, en clair, sans rien envoyer -- comme le bouton
            # de recherche le fait deja. C'est la faculte qui envoie le plus :
            # le rapport du jour et tout le fil.
            "apercu": apercu(contexte_pour_analyse(self.notice()), fil, "<ta question>"),
            "tours": fil.tours,
            "restants": Quota().restants(),
            "plafond": PLAFOND_PAR_JOUR,
            "bilan": phrase_de_bilan(compte),
            "usd": compte["usd"],
            "restant_usd": compte["restant_usd"],
        }

    @staticmethod
    def _garde_le_budget(quota: Any, bilan: Any, tarifs: Any, *, commande: str) -> None:
        """Ce qui protège ses cinq dollars, écrit une fois pour les deux routes.

        La vraie garde, quand il a donné ses tarifs : l'argent. Le plafond de
        tours protège d'un emballement -- une poche, une soirée distraite --
        mais c'est le crédit qui s'épuise pour de bon, et le service refuserait
        de toute façon, une requête plus tard et sans le dire aussi clairement.

        C'est une estimation, faite avec ses chiffres. S'il la trouve fausse,
        c'est `credit_usd` dans son fichier de tarifs qu'il corrige, pas ce
        code.

        `restant_au_mieux_usd` et pas `restant_usd` : le second vaut None dès
        qu'un modèle n'a pas de tarif, et la garde s'éteignait alors en
        silence -- une seule recherche suffisait.

        Ces deux refus vivaient en double, commentaire compris, dans la route
        de la conversation et dans celle des offres. Deux copies d'une garde
        qui compte de l'argent : corriger l'une laisse l'autre payer. Le seul
        écart légitime entre elles est la commande à taper depuis le clavier,
        alors c'est le seul paramètre.

        Le quota est le même fichier pour les deux facultés, d'où « le plafond
        du jour » : c'est bien un seul plafond, partagé.
        """
        restant = bilan(quota, tarifs())["restant_au_mieux_usd"]
        if restant is not None and restant <= 0:
            raise SageError(
                HTTPStatus.PAYMENT_REQUIRED,
                "d'après tes tarifs, ton crédit est épuisé. Recharge sur "
                "console.anthropic.com, puis corrige « credit_usd » dans "
                "ton fichier de tarifs.",
            )
        if quota.restants() <= 0:
            raise SageError(
                HTTPStatus.TOO_MANY_REQUESTS,
                "le plafond du jour est atteint. Demain, ou depuis le clavier "
                f"avec « python3 -m singular {commande} ».",
            )

    def parle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Un tour de conversation. La seule route qui coûte de l'argent.

        Trois refus avant la dépense, dans cet ordre : une question vide ou
        démesurée ne part pas ; un tour déjà en cours refuse le second ; le
        plafond du jour refuse le vingt-et-unième. Ensuite seulement le
        service est appelé.

        Le tour n'est compté qu'au retour. Une faculté coupée -- pas de clé,
        pas de paquet, pas de réseau -- n'a rien dépensé et ne doit rien
        coûter de la journée.
        """
        from ..analyse import AnalyseIndisponible, contexte_pour_analyse
        from ..parle import (
            MODELE_PAR_DEFAUT,
            Conversation,
            PlafondAtteint,
            Quota,
            Tarifs,
            bilan,
            repondre,
        )

        question = _text(payload, "question")
        if len(question) > QUESTION_MAX:
            raise SageError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            f"une question tient en {QUESTION_MAX} caractères")

        if not self._un_tour.acquire(blocking=False):
            raise SageError(HTTPStatus.CONFLICT,
                            "une réponse est déjà en train d'arriver. Laisse-la venir.")
        try:
            quota = Quota()
            self._garde_le_budget(quota, bilan, Tarifs, commande="parle")
            # Le fil est relu du disque a chaque tour : la ligne de commande
            # ecrit le meme fichier, et repartir de ce qu'on avait en memoire
            # ferait disparaitre ce qui s'est dit ailleurs.
            fil = Conversation()
            try:
                texte, cout = repondre(question, contexte_pour_analyse(self.notice()), fil)
            except AnalyseIndisponible as exc:
                raise SageError(HTTPStatus.SERVICE_UNAVAILABLE, str(exc)) from None
            fil.sauver()
            try:
                restants = quota.consommer(cout=cout, modele=MODELE_PAR_DEFAUT)
            except PlafondAtteint:
                # Le compteur s'est rempli entre la verification et ici : un
                # second serveur sur la meme machine, ou la ligne de commande.
                # La reponse est payee et ecrite dans le fil ; la perdre pour
                # un compteur serait le seul vrai degat de la situation.
                restants = 0
        finally:
            self._un_tour.release()
        # Le bilan est relu apres le decompte : c'est le seul moment ou il
        # inclut le tour qu'on vient de payer.
        return {"reponse": texte, "cout": cout, "restants": restants,
                **{cle: valeur for cle, valeur in self.parle_etat().items()
                   if cle in ("bilan", "usd", "restant_usd")}}

    def offres_etat(self) -> dict[str, Any]:
        """Ce qui partirait, et ce qu'il reste. Gratuit, sans clé, sans SDK.

        Le contexte est rendu en entier parce qu'il parle de lui : il a le
        droit de lire ce qui quitte sa machine avant que ça la quitte, et
        `python3 -m singular offres --blanc` le lui montre déjà au clavier.
        """
        RECHERCHES_MAX, apercu = _faculte_offres("RECHERCHES_MAX", "apercu")
        from ..parle import PLAFOND_PAR_JOUR, Quota, bilan, phrase_de_bilan

        quota = Quota()
        compte = bilan(quota)
        return {
            "contexte": apercu(),
            "recherches_max": RECHERCHES_MAX,
            "restants": quota.restants(),
            "plafond": PLAFOND_PAR_JOUR,
            "bilan": phrase_de_bilan(compte),
            "restant_usd": compte["restant_usd"],
        }

    def offres(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Il cherche, il écarte, il propose. Il ne postule pas, et il n'écrit rien.

        Cette route ne touche pas au journal, et ne peut pas y toucher : elle
        rend du texte. `tests/test_sage_isolation.py` tient l'invariant du
        dépôt sur les imports plutôt que sur les intentions -- penser n'est pas
        décider, décider n'est pas autoriser.

        Les gardes sont celles de `parle`, et pour les mêmes raisons, à une
        près : une recherche coûte nettement plus qu'un tour de conversation,
        parce que chaque recherche web ramène des pages entières. Le verrou est
        donc le même objet que celui de la conversation -- ce n'est pas une
        économie de code, c'est le même porte-monnaie : lancer une recherche
        pendant qu'une réponse arrive dépenserait deux fois sur un crédit qui
        n'a été vérifié qu'une.
        """
        from ..analyse import AnalyseIndisponible
        MODELE_PAR_DEFAUT, chercher = _faculte_offres("MODELE_PAR_DEFAUT", "chercher")
        from ..parle import PlafondAtteint, Quota, Tarifs, bilan

        precision = payload.get("precision", "")
        if not isinstance(precision, str):
            raise SageError(HTTPStatus.BAD_REQUEST, "« precision » doit être du texte")
        if len(precision) > QUESTION_MAX:
            raise SageError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            f"une précision tient en {QUESTION_MAX} caractères")

        if not self._un_tour.acquire(blocking=False):
            raise SageError(HTTPStatus.CONFLICT,
                            "une réponse est déjà en train d'arriver. Laisse-la venir.")
        try:
            quota = Quota()
            self._garde_le_budget(quota, bilan, Tarifs, commande="offres")
            try:
                texte, cout = chercher(precision)
            except AnalyseIndisponible as exc:
                raise SageError(HTTPStatus.SERVICE_UNAVAILABLE, str(exc)) from None
            try:
                restants = quota.consommer(cout=cout, modele=MODELE_PAR_DEFAUT)
            except PlafondAtteint:
                # La recherche est payee. La perdre pour un compteur qui s'est
                # rempli entre-temps serait le seul vrai degat de la situation.
                restants = 0
        finally:
            self._un_tour.release()
        return {"offres": texte, "cout": cout, "restants": restants,
                **{cle: valeur for cle, valeur in self.offres_etat().items()
                   if cle in ("bilan", "restant_usd")}}

    def parle_oubli(self) -> dict[str, Any]:
        """Efface le fil. Le journal ne bouge pas, et le plafond non plus."""
        from ..parle import Conversation

        Conversation().oublier()
        return self.parle_etat()

    # --- routage -------------------------------------------------------------

    def route(self, method: str, path: str, query: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        if method == "GET" and path == "/api/notice":
            return self.notice()
        if method == "GET" and path == "/api/collecte":
            return self.collecte()
        if method == "GET" and path == "/api/entries":
            return self.entries(query.get("status"))
        if method == "POST" and path == "/api/entries":
            return self.add(body)
        if method == "GET" and path == "/api/parle":
            return self.parle_etat()
        if method == "POST" and path == "/api/parle":
            return self.parle(body)
        if method == "POST" and path == "/api/parle/oubli":
            return self.parle_oubli()
        if method == "GET" and path == "/api/offres":
            return self.offres_etat()
        if method == "POST" and path == "/api/offres":
            return self.offres(body)
        matched = re.fullmatch(r"/api/entries/([^/]+)/(resolve|abandon)", path)
        if matched and method == "POST":
            entry_id = matched.group(1)
            if not ENTRY_ID.fullmatch(entry_id):
                raise SageError(HTTPStatus.BAD_REQUEST, "identifiant de décision invalide")
            if matched.group(2) == "resolve":
                return self.resolve(entry_id, body)
            return self.abandon(entry_id, body)
        raise SageError(HTTPStatus.NOT_FOUND, "route inconnue")

    def authorised(self, client_host: str, query: dict[str, str], header_token: str) -> bool:
        """Le jeton, sauf depuis la machine elle-même.

        Sur la boucle locale il n'y a personne d'autre : demander un jeton pour
        `127.0.0.1` n'ajoute rien et fait échouer le cas où on l'a perdu.

        Ailleurs, l'absence de jeton **refuse**. Elle autorisait, et c'était la
        faille : la garde dépendait de la façon dont on avait demandé le
        démarrage -- l'option `--lan`, qui seule créait un jeton -- et non de ce
        que le serveur exposait réellement. `--host 0.0.0.0` sans `--lan`
        écoutait donc tout le réseau avec `token = ""`, et servait le journal
        personnel à qui le demandait. Une propriété de sécurité déduite d'une
        intention plutôt que d'un fait.
        """
        if client_host in LOOPBACK:
            return True
        if not self.token:
            return False
        supplied = header_token or query.get("k", "")
        return secrets.compare_digest(supplied, self.token)


class SageHandler(BaseHTTPRequestHandler):
    """Le peu de HTTP dont l'app a besoin."""

    server_version = "SINGULAR-Sage"
    app: SageApp

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002 - signature imposée
        return  # un journal de décisions n'a pas à tenir un journal d'accès

    # --- envoi ---------------------------------------------------------------

    def _send(self, status: HTTPStatus, body: bytes, content_type: str, *, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        # L'app ne charge rien d'extérieur : tout est servi par ce processus.
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; base-uri 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    # --- réception -----------------------------------------------------------

    def _split(self) -> tuple[str, dict[str, str]]:
        raw_path, _, raw_query = self.path.partition("?")
        query: dict[str, str] = {}
        for part in raw_query.split("&"):
            if not part:
                continue
            name, _, value = part.partition("=")
            query[unquote_plus(name)] = unquote_plus(value)
        return raw_path, query

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise SageError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "requête trop grande")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SageError(HTTPStatus.BAD_REQUEST, "corps de requête illisible") from None
        if not isinstance(payload, dict):
            raise SageError(HTTPStatus.BAD_REQUEST, "le corps doit être un objet JSON")
        return payload

    def _static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        if path in {"/icon-180.png", "/icon-512.png"}:
            size = 180 if path.endswith("180.png") else 512
            self._send(HTTPStatus.OK, render_icon(size), "image/png", cache="public, max-age=86400")
            return
        target = (WEB_ROOT / path.lstrip("/")).resolve()
        if not target.is_file() or WEB_ROOT.resolve() not in target.parents:
            raise SageError(HTTPStatus.NOT_FOUND, "page inconnue")
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(HTTPStatus.OK, target.read_bytes(), content_type)

    def _refuse_another_page(self) -> None:
        """Le jeton dit qui sait ; il ne dit pas qui demande.

        Une page web ouverte sur cette machine parle depuis `127.0.0.1`, et
        `authorised` accorde tout à la boucle locale parce qu'il n'y a
        « personne d'autre » dessus. Il y a le navigateur. N'importe quelle
        page consultée pendant que le Sage tourne pouvait donc écrire dans le
        journal, et surtout rendre un verdict -- sans connaître le jeton, sans
        rien afficher, et en faussant la calibration, qui est tout l'intérêt de
        l'outil. Reproduit avant d'être corrigé.

        C'est l'invariant du projet pris à revers : le Sage ne décide pas à ta
        place, mais un site quelconque le faisait.

        Trois faits que la page appelante ne contrôle pas la refusent : le nom
        par lequel on nous appelle, qui doit être une adresse et non un domaine
        qu'on aurait fait pointer ici ; l'origine que le navigateur déclare ; et
        le type du corps, dont le JSON exige une permission préalable que ce
        serveur ne donne pas.
        """
        host = self.headers.get("Host", "")
        if not host_is_an_address(host):
            raise SageError(HTTPStatus.FORBIDDEN, "ce serveur ne répond qu'à son adresse")
        if not same_origin(self.headers.get("Origin", ""), host):
            raise SageError(HTTPStatus.FORBIDDEN, "requête venue d'une autre page")
        if self.command == "POST":
            declared = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if declared != JSON_BODY:
                raise SageError(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    f"le corps doit être annoncé « {JSON_BODY} »",
                )

    def _handle(self) -> None:
        """Le jeton garde le journal, pas la coquille qui l'affiche.

        Il gardait tout, et l'app était inutilisable depuis le téléphone. La
        page s'ouvre avec `?k=...`, mais le navigateur va ensuite chercher
        `app.css`, `app.js`, le manifeste et les icônes **par lui-même**, avec
        des adresses relatives qui ne portent pas le jeton. Toutes étaient
        refusées : on obtenait le titre sans mise en forme, sans données, et
        rien n'indiquait pourquoi.

        Le découpage est celui de ce qu'on protège. Derrière `/api/` il y a ce
        que tu as écrit : jeton obligatoire dès qu'on vient d'ailleurs que de
        cette machine. Devant, il y a des fichiers identiques pour tout le
        monde, lus tels quels sur le disque, publics dans le dépôt, et qui ne
        contiennent aucune décision -- `test_sage_server.py` interdit qu'ils
        en contiennent jamais. Les servir n'apprend rien à personne.
        """
        path, query = self._split()
        if path.startswith("/api/"):
            self._refuse_another_page()
            client = self.client_address[0] if self.client_address else ""
            if not self.app.authorised(client, query, self.headers.get("X-Sage-Token", "")):
                self._json(HTTPStatus.UNAUTHORIZED, {"message": "jeton d'accès manquant ou invalide"})
                return
            self._json(HTTPStatus.OK, self.app.route(self.command, path, query, self._body()))
            return
        if self.command not in {"GET", "HEAD"}:
            raise SageError(HTTPStatus.METHOD_NOT_ALLOWED, "méthode non autorisée ici")
        self._static(path)

    def _dispatch(self) -> None:
        try:
            self._handle()
        except SageError as exc:
            self._json(exc.status, {"message": exc.message})
        except Exception as exc:  # noqa: BLE001 - un serveur personnel ne doit jamais tomber
            # La panne se lit dans la fenetre du serveur, ou il peut la copier ; le telephone
            # recoit une phrase. `OperationalError: database is locked` ne dit
            # rien a personne, et c'etait la derniere porte par ou un message
            # de bibliotheque arrivait sur son ecran.
            print(f"\n  [Sage] {type(exc).__name__}: {exc}", flush=True)
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": _panne(exc)})

    def do_GET(self) -> None:  # noqa: N802 - signature imposée
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()


#: Ce qu'on dit d'une panne qu'on ne sait pas nommer.
PANNE = ("Quelque chose a cassé de mon côté. Le détail est écrit dans la fenêtre "
         "où tourne le Sage. Ton journal, lui, n'a pas bougé.")

#: Et la seule panne courante qu'il peut lui-meme resoudre.
OCCUPE = ("Le journal est occupé par une autre fenêtre -- une commande en cours "
          "sur ton Mac. Réessaie dans un instant.")


def _panne(exc: Exception) -> str:
    """Une phrase pour le telephone, dans sa langue.

    Le corps JSON portait `f"{type(exc).__name__}: {exc}"`, donc
    `OperationalError: database is locked` s'affichait sur son ecran. C'est le
    meme defaut que les refus de saisie et les refus d'ecriture, a la derniere
    porte : celle des pannes qu'on n'a pas prevues.
    """
    if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc):
        return OCCUPE
    return PANNE


def build_server(app: SageApp, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundSageHandler", (SageHandler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def same_origin(origin: str, host_header: str) -> bool:
    """La page qui appelle est-elle celle que ce serveur a servie ?

    `Origin` et `Host` sont tous deux posés par le navigateur et hors d'atteinte
    de la page qui s'exécute dedans : les comparer dit d'où vient réellement la
    requête, ce que le jeton ne dit pas.

    Absent vaut oui. Un navigateur omet `Origin` sur les lectures de même
    origine, et un client qui n'est pas un navigateur -- `curl`, l'app native --
    n'en envoie jamais : ceux-là ne portent aucune session à détourner, puisque
    c'est le navigateur, et lui seul, qui joint automatiquement le contexte de
    la machine à une requête qu'il n'a pas voulue.

    `null` vaut non : c'est ce qu'annonce une page sans origine propre, et il
    n'y a aucune raison qu'une telle page parle au journal.
    """
    if not origin:
        return True
    parsed = urlsplit(origin)
    if parsed.scheme != "http" or not parsed.netloc:
        return False
    return parsed.netloc == host_header.strip()


def host_is_an_address(host_header: str) -> bool:
    """Le nom par lequel on nous appelle est-il une adresse, et non un domaine ?

    Sans cette question, comparer `Origin` et `Host` ne suffit pas. Un attaquant
    qui fait pointer son propre domaine vers cette machine, et qui sert sa page
    sur le même port, obtient une origine et un hôte identiques : la
    comparaison dit « même origine » alors que la page est la sienne. Le
    navigateur, lui, la croit chez elle et lui laisse tout.

    Ce serveur n'a pas de nom : on l'atteint par `127.0.0.1`, par `localhost`,
    ou par l'adresse de la machine sur le wifi. Un domaine dans `Host` ne peut
    donc désigner que quelqu'un qui s'est arrangé pour y arriver.
    """
    host = host_header.strip()
    if not host:
        return False
    if host.startswith("["):  # IPv6 entre crochets, avec ou sans port
        host = host.partition("]")[0].removeprefix("[")
    elif host.count(":") == 1:
        host = host.partition(":")[0]
    if host.lower() == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def is_loopback_bind(host: str) -> bool:
    """L'adresse d'écoute reste-t-elle sur cette machine ?

    C'est le fait dont dépend la sécurité du serveur, et il se lit ici plutôt
    que dans l'option qu'on a tapée.
    """
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost", ""}


def _port_refuse(refus: OSError, port: int) -> int:
    """Le systeme refuse le port. Le dire, plutot que derouler une pile Python.

    Le cas est celui de tous les matins : `A_FAIRE.md` demande de lancer le
    Sage chaque jour, et une fenetre laissee ouverte la veille tient encore le
    port. Python deroulait alors huit lignes de pile finissant par
    `OSError: [Errno 98] Address already in use` -- pour quelqu'un qui debute
    en code, c'est indistinguable d'une application cassee, et la vraie reponse
    tient en une phrase : elle tourne deja, ouvre l'adresse.
    """
    if refus.errno == errno.EADDRINUSE:
        print(f"\n  Le port {port} est déjà pris.")
        print("  Le Sage tourne probablement déjà dans une autre fenêtre :")
        print(f"  ouvre http://127.0.0.1:{port}/ pour vérifier.")
        print(f"\n  Sinon, choisis un autre port : --port {port + 1}\n")
        return 1
    if refus.errno == errno.EACCES:
        print(f"\n  Le système refuse le port {port}.")
        print(f"  Choisis un port au-dessus de 1024 : --port {max(port, 8765)}\n")
        return 1
    raise refus


def serve(*, db: str | Path = DEFAULT_PATH, host: str = "127.0.0.1", port: int = 8765, lan: bool = False) -> int:
    """Démarrer le Sage. Affiche l'adresse à ouvrir, y compris depuis le téléphone."""
    journal = DecisionJournal(db)
    bind = "0.0.0.0" if lan else host  # noqa: S104 - exposition demandée, et protégée par un jeton
    exposed = not is_loopback_bind(bind)
    # Le jeton suit l'exposition réelle, pas l'option choisie : `--host 0.0.0.0`
    # expose autant que `--lan` et doit être protégé pareil.
    token = read_token() if exposed else ""
    app = SageApp(journal, token=token)
    try:
        server = build_server(app, bind, port)
    except OSError as refus:
        return _port_refuse(refus, port)
    started = datetime.now().strftime("%H:%M")

    print(f"\n  SINGULAR · le Sage        démarré à {started}")
    print(f"  sur cette machine         http://127.0.0.1:{port}/")
    if exposed:
        print(f"  depuis ton iPhone         http://{local_address()}:{port}/?k={token}")
        print("\n  Sur l'iPhone : ouvre cette adresse dans Safari, puis Partager, puis")
        print("  « Sur l'écran d'accueil ». Tu auras une icône, sans barre de navigateur.")
        print("\n  Le jeton dans l'adresse protège ton journal des autres appareils du wifi.")
        print("  Sans lui, toute requête venue d'ailleurs que de cette machine est refusée.")
    else:
        print("\n  Pour y accéder depuis ton iPhone : relance avec --lan")
    # L'etat de la conversation, au demarrage plutot qu'au moment ou il appuie.
    # Une cle oubliee ne se voit qu'une fois le telephone en main, loin du
    # clavier. La phrase vient de la faculte, et elle donne la commande : ici,
    # on n'a pas le droit d'ecrire le nom d'une variable de cle, et un test le
    # verifie.
    from ..parle import etat_de_la_faculte  # importe ici : le Sage marche sans

    print(f"\n  {etat_de_la_faculte()[1]}")
    print("\n  Ctrl+C pour arrêter.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arrêté.\n")
    finally:
        server.server_close()
    return 0


__all__ = ["SageApp", "SageError", "SageHandler", "build_server", "is_loopback_bind",
           "host_is_an_address", "local_address", "read_token", "same_origin", "serve"]
