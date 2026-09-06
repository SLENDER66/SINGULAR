"""Le serveur du Sage : une app web, installable sur l'écran d'accueil.

Pourquoi une app web et pas une app iOS : une app native demande un Mac, Xcode
et un compte développeur Apple. Une PWA ajoutée à l'écran d'accueil depuis
Safari donne une icône, le plein écran et, depuis iOS 16.4, les notifications --
sans rien de tout ça.

Pourquoi la bibliothèque standard et pas un framework : ce serveur doit démarrer
sur un PC Windows où rien n'est installé, avec une seule commande et zéro
`pip install`. Un outil qui demande une installation avant de servir est un
outil qu'on n'ouvre pas.

Ce serveur lit et écrit le journal. Il n'importe rien de la frontière
d'exécution -- un test le vérifie -- de sorte qu'aucune requête HTTP ne peut
déclencher d'action sur le monde. Le Sage observe et conseille ; toi seul
décides.
"""
from __future__ import annotations

import json
import re
import secrets
import socket
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

from ..journal import DEFAULT_PATH, DecisionJournal, Status, Tier
from .icon import render_icon
from .notice import build_notice

WEB_ROOT = Path(__file__).parent / "web"
TOKEN_PATH = DEFAULT_PATH.parent / "sage_token"

#: Un corps de requête plus gros que ça n'est pas une décision de journal.
MAX_BODY = 64 * 1024

#: Les seules adresses qui n'ont pas besoin du jeton : elles ne peuvent venir
#: que de la machine elle-même.
LOOPBACK = frozenset({"127.0.0.1", "::1"})

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
            return existing
    token = secrets.token_urlsafe(18)
    path.write_text(token, encoding="utf-8")
    return token


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
        "lesson": entry.lesson or "",
        "brier_score": entry.brier_score,
    }


class SageApp:
    """Le routage et la logique, sans rien qui touche à HTTP.

    Séparé du gestionnaire de requêtes pour que les tests appellent les routes
    directement : un test qui monte un vrai serveur pour vérifier une règle
    métier teste surtout le serveur.
    """

    def __init__(self, journal: DecisionJournal, *, token: str = "") -> None:
        self.journal = journal
        self.token = token

    # --- lecture -------------------------------------------------------------

    def notice(self) -> dict[str, Any]:
        return build_notice(self.journal).as_dict()

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
        try:
            entry = self.journal.add(
                title=_text(payload, "title"),
                action=_text(payload, "action"),
                predicted=_text(payload, "predicted"),
                probability=_number(payload, "probability", cast=float),
                tier=_tier(payload.get("tier", Tier.REVENUS.value)),
                cost_hours=_number(payload, "cost_hours", cast=float),
                horizon_days=_number(payload, "horizon_days", cast=int),
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
            raise SageError(HTTPStatus.NOT_FOUND, f"{entry_id} n'existe pas") from None
        except PermissionError as exc:
            raise SageError(HTTPStatus.CONFLICT, str(exc)) from None
        return _entry_as_dict(entry)

    def abandon(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            entry = self.journal.abandon(entry_id, reason=_text(payload, "reason"))
        except KeyError:
            raise SageError(HTTPStatus.NOT_FOUND, f"{entry_id} n'existe pas") from None
        except PermissionError as exc:
            raise SageError(HTTPStatus.CONFLICT, str(exc)) from None
        return _entry_as_dict(entry)

    # --- routage -------------------------------------------------------------

    def route(self, method: str, path: str, query: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        if method == "GET" and path == "/api/notice":
            return self.notice()
        if method == "GET" and path == "/api/entries":
            return self.entries(query.get("status"))
        if method == "POST" and path == "/api/entries":
            return self.add(body)
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

    def _handle(self) -> None:
        path, query = self._split()
        client = self.client_address[0] if self.client_address else ""
        if not self.app.authorised(client, query, self.headers.get("X-Sage-Token", "")):
            self._json(HTTPStatus.UNAUTHORIZED, {"message": "jeton d'accès manquant ou invalide"})
            return
        if path.startswith("/api/"):
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
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"{type(exc).__name__}: {exc}"})

    def do_GET(self) -> None:  # noqa: N802 - signature imposée
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()


def build_server(app: SageApp, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundSageHandler", (SageHandler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def is_loopback_bind(host: str) -> bool:
    """L'adresse d'écoute reste-t-elle sur cette machine ?

    C'est le fait dont dépend la sécurité du serveur, et il se lit ici plutôt
    que dans l'option qu'on a tapée.
    """
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost", ""}


def serve(*, db: str | Path = DEFAULT_PATH, host: str = "127.0.0.1", port: int = 8765, lan: bool = False) -> int:
    """Démarrer le Sage. Affiche l'adresse à ouvrir, y compris depuis le téléphone."""
    journal = DecisionJournal(db)
    bind = "0.0.0.0" if lan else host  # noqa: S104 - exposition demandée, et protégée par un jeton
    exposed = not is_loopback_bind(bind)
    # Le jeton suit l'exposition réelle, pas l'option choisie : `--host 0.0.0.0`
    # expose autant que `--lan` et doit être protégé pareil.
    token = read_token() if exposed else ""
    app = SageApp(journal, token=token)
    server = build_server(app, bind, port)
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
    print("\n  Ctrl+C pour arrêter.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Arrêté.\n")
    finally:
        server.server_close()
    return 0


__all__ = ["SageApp", "SageError", "SageHandler", "build_server", "is_loopback_bind",
           "local_address", "read_token", "serve"]
