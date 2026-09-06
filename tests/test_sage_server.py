"""Le Sage expose un journal personnel sur le réseau. Ce qu'il refuse compte.

Ce serveur a été écrit sans ces tests, et la faille est arrivée exactement là où
on l'attendait : la garde d'accès dépendait de l'option qu'on avait tapée
(`--lan`, la seule à créer un jeton) et non de l'adresse réellement écoutée.
`--host 0.0.0.0` servait donc le journal à tout le wifi, sans authentification,
sans que rien ne le signale.

Une propriété de sécurité déduite d'une intention plutôt que d'un fait tient
jusqu'au jour où quelqu'un atteint le fait par un autre chemin. Les tests
d'accès portent donc sur le fait -- l'adresse du client, l'adresse d'écoute --
et pas sur les options.
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest

from singular.journal import DecisionJournal, Status, Tier
from singular.sage.server import (
    MAX_BODY,
    SageApp,
    SageError,
    build_server,
    host_is_an_address,
    is_loopback_bind,
    read_token,
    same_origin,
)

TOKEN = "un-jeton-de-test-suffisamment-long"


@pytest.fixture
def journal(tmp_path):
    return DecisionJournal(tmp_path / "journal.db")


@pytest.fixture
def app(journal):
    return SageApp(journal, token=TOKEN)


# --- qui a le droit de lire --------------------------------------------------

@pytest.mark.parametrize("client", ["127.0.0.1", "::1"])
def test_the_machine_itself_needs_no_token(app, client):
    """Sur la boucle locale il n'y a personne d'autre, et un jeton perdu
    n'a pas à enfermer son propriétaire dehors."""
    assert app.authorised(client, {}, "") is True


@pytest.mark.parametrize("client", ["192.168.1.57", "10.0.0.4", "203.0.113.9"])
def test_another_machine_needs_the_token(app, client):
    assert app.authorised(client, {}, "") is False
    assert app.authorised(client, {}, "mauvais") is False
    assert app.authorised(client, {"k": "mauvais"}, "") is False
    assert app.authorised(client, {}, TOKEN) is True
    assert app.authorised(client, {"k": TOKEN}, "") is True


def test_no_token_refuses_instead_of_allowing(journal):
    """La régression exacte : sans jeton, tout le réseau était servi.

    L'absence de jeton signifiait « pas de protection demandée », donc
    « autorise » — alors qu'elle ne peut vouloir dire qu'une chose côté
    serveur : rien ne permet de distinguer ce client du propriétaire.
    """
    open_app = SageApp(journal, token="")
    assert open_app.authorised("127.0.0.1", {}, "") is True
    for stranger in ("192.168.1.57", "10.0.0.4", "203.0.113.9"):
        assert open_app.authorised(stranger, {}, "") is False, (
            f"{stranger} lit le journal personnel sans rien présenter"
        )


@pytest.mark.parametrize(
    "host,loopback",
    [("127.0.0.1", True), ("localhost", True), ("::1", True), ("", True),
     ("0.0.0.0", False), ("192.168.1.57", False), ("  0.0.0.0  ", False)],
)
def test_exposure_is_read_from_the_bind_address(host, loopback):
    """C'est ce fait-là qui décide qu'un jeton est nécessaire, pas une option."""
    assert is_loopback_bind(host) is loopback


def test_the_token_survives_a_restart(tmp_path):
    """Sinon l'app installée sur le téléphone perdrait l'accès à chaque relance."""
    path = tmp_path / "sage_token"
    first = read_token(path)
    assert len(first) >= 20
    assert read_token(path) == first


# --- ce que les routes refusent ----------------------------------------------

def test_an_unknown_route_is_refused(app):
    with pytest.raises(SageError) as refusal:
        app.route("GET", "/api/inventé", {}, {})
    assert refusal.value.status == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("forged", ["DEC-XXXX", "DEC-", "DEC-deadbeefff", "",
                                    "'; DROP TABLE journal_entries;--",
                                    "..%2f..%2fetc%2fpasswd"])
def test_a_forged_entry_id_is_refused_before_the_journal(app, forged):
    """La forme de l'identifiant est vérifiée avant toute lecture.

    Le séparateur encodé en `%2f` mérite d'être ici : c'est le contournement
    classique d'un routage qui décode avant de router. Celui-ci ne décode pas le
    chemin, donc `%2f` reste littéral et la garde de forme l'attrape.
    """
    with pytest.raises(SageError) as refusal:
        app.route("POST", f"/api/entries/{forged}/resolve", {}, {"happened": True})
    assert refusal.value.status in {HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND}
    assert "n'existe pas" not in refusal.value.message, (
        "l'identifiant a été porté jusqu'au journal au lieu d'être refusé sur sa forme"
    )


@pytest.mark.parametrize("forged", ["../../etc/passwd", "a/b"])
def test_an_id_carrying_a_separator_matches_no_route_at_all(app, forged):
    """Le chemin ne ressemble plus à la route : il est refusé avant d'être lu."""
    with pytest.raises(SageError, match="route inconnue"):
        app.route("POST", f"/api/entries/{forged}/resolve", {}, {"happened": True})


def test_certainty_is_refused_through_the_api(app):
    """La règle du journal doit valoir aussi par le réseau."""
    payload = {"title": "A", "action": "a", "predicted": "p", "probability": 1.0,
               "tier": "REVENUS", "cost_hours": 1, "horizon_days": 7}
    with pytest.raises(SageError) as refusal:
        app.add(payload)
    assert refusal.value.status == HTTPStatus.BAD_REQUEST
    assert "certainty" in refusal.value.message or "probability" in refusal.value.message


def test_blank_fields_are_refused(app):
    base = {"title": "A", "action": "a", "predicted": "p", "probability": 0.5,
            "tier": "REVENUS", "cost_hours": 1, "horizon_days": 7}
    for field in ("title", "action", "predicted"):
        with pytest.raises(SageError):
            app.add({**base, field: "   "})


def test_an_unknown_tier_is_refused(app):
    with pytest.raises(SageError, match="rang inconnu"):
        app.add({"title": "A", "action": "a", "predicted": "p", "probability": 0.5,
                 "tier": "LIBERTE_TOTALE", "cost_hours": 1, "horizon_days": 7})


def test_a_verdict_cannot_be_rewritten_through_the_api(app, journal):
    entry = journal.add(title="A", action="a", predicted="p", probability=0.6,
                        tier=Tier.REVENUS, cost_hours=1.0, horizon_days=7)
    app.resolve(entry.entry_id, {"happened": True})
    with pytest.raises(SageError) as refusal:
        app.resolve(entry.entry_id, {"happened": False})
    assert refusal.value.status == HTTPStatus.CONFLICT


def test_a_missing_entry_is_not_found(app):
    with pytest.raises(SageError) as refusal:
        app.resolve("DEC-deadbeef", {"happened": True})
    assert refusal.value.status == HTTPStatus.NOT_FOUND


def test_happened_must_be_a_boolean(app, journal):
    entry = journal.add(title="A", action="a", predicted="p", probability=0.6,
                        tier=Tier.REVENUS, cost_hours=1.0, horizon_days=7)
    for value in ("oui", 1, None, {}):
        with pytest.raises(SageError, match="vrai ou faux"):
            app.resolve(entry.entry_id, {"happened": value})


def test_writing_through_the_api_keeps_the_chain_intact(app, journal):
    app.add({"title": "Négocier", "action": "demander", "predicted": "accepté",
             "probability": 0.4, "tier": "REVENUS", "cost_hours": 2, "horizon_days": 30})
    entry_id = journal.entries()[0].entry_id
    app.resolve(entry_id, {"happened": True, "lesson": "posé, ça passe"})
    assert journal.verify() is True


# --- le serveur réel ---------------------------------------------------------

@pytest.fixture
def running(app):
    server = build_server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _raw_request(base: str, request_line: str) -> str:
    """Envoyer une ligne de requête telle quelle, sans normalisation d'urllib."""
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(f"{request_line}\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        return sock.recv(4096).decode("utf-8", "replace")


@pytest.mark.parametrize("target", [
    "/../../../../etc/passwd",
    "/../singular/journal.py",
    "/web/../../../etc/hostname",
    "//etc/passwd",
])
def test_no_path_escapes_the_web_directory(running, target):
    """urllib normaliserait ces chemins ; une socket brute, non."""
    response = _raw_request(running, f"GET {target} HTTP/1.1")
    assert " 404 " in response.splitlines()[0], response.splitlines()[0]
    assert "root:" not in response and "import" not in response


def test_the_app_shell_and_its_assets_are_served(running):
    for path, marker in [("/", "SINGULAR"), ("/app.js", "Notice"), ("/manifest.webmanifest", "standalone")]:
        with urllib.request.urlopen(running + path) as response:
            assert response.status == 200
            assert marker in response.read().decode("utf-8")


def test_the_icon_is_a_real_png(running):
    with urllib.request.urlopen(running + "/icon-180.png") as response:
        assert response.read()[:8] == b"\x89PNG\r\n\x1a\n"


def test_an_oversized_body_is_refused_before_being_read(running):
    request = urllib.request.Request(
        running + "/api/entries", data=b"{}" + b" " * (MAX_BODY + 1),
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(request)
    assert refusal.value.code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_an_unreadable_body_is_refused(running):
    request = urllib.request.Request(
        running + "/api/entries", data=b"{ceci n'est pas du json",
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(request)
    assert refusal.value.code == HTTPStatus.BAD_REQUEST


def test_a_json_body_that_is_not_an_object_is_refused(running):
    request = urllib.request.Request(
        running + "/api/entries", data=b'["une liste"]',
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(request)
    assert refusal.value.code == HTTPStatus.BAD_REQUEST


def test_writing_to_a_static_path_is_refused(running):
    request = urllib.request.Request(running + "/index.html", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(request)
    assert refusal.value.code == HTTPStatus.METHOD_NOT_ALLOWED


def test_a_refusal_answers_in_json_rather_than_a_stack_trace(running):
    request = urllib.request.Request(running + "/api/entries", data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(request)
    body = json.loads(refusal.value.read())
    assert "message" in body
    assert "Traceback" not in body["message"]


# --- ce que le jeton garde, et ce qu'il n'a jamais eu à garder ---------------

@pytest.fixture
def from_the_network(journal):
    """Un serveur joint depuis une vraie adresse réseau, pas la boucle locale.

    Tous les autres tests d'assets passent par `127.0.0.1`, où le jeton n'est
    pas demandé. C'est ce qui a laissé passer la panne : le serveur exigeait le
    jeton pour tout, y compris `app.css` et `app.js`, que le navigateur va
    chercher par lui-même avec des adresses relatives qui ne le portent pas.
    Depuis un téléphone, l'app s'ouvrait sans mise en forme et sans données, et
    rien ne disait pourquoi. Depuis la machine, tout marchait.
    """
    from singular.sage.server import local_address

    address = local_address()
    if address in {"127.0.0.1", "::1"}:
        pytest.skip("aucune adresse non-loopback : ce test a besoin d'un vrai réseau")

    entry = journal.add(title="Titre confidentiel MARQUEUR-TITRE", action="faire",
                        predicted="résultat MARQUEUR-PREDIT", probability=0.42,
                        tier=Tier.REVENUS, cost_hours=3, horizon_days=7)
    journal.resolve(entry.entry_id, happened=False, lesson="leçon MARQUEUR-LECON")

    server = build_server(SageApp(journal, token=TOKEN), "0.0.0.0", 0)  # noqa: S104 - le test veut l'exposition
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://{address}:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _fetch(base: str, path: str, token: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(base + path)
    if token is not None:
        request.add_header("X-Sage-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read()


@pytest.mark.parametrize("asset", ["/", "/app.css", "/app.js", "/manifest.webmanifest",
                                   "/icon-180.png"])
def test_the_shell_loads_from_the_network_without_the_token(from_the_network, asset):
    """Le navigateur ne peut pas faire autrement : il demande ces fichiers seul."""
    status, body = _fetch(from_the_network, asset)
    assert status == HTTPStatus.OK, f"{asset} refusé : l'app resterait nue sur le téléphone"
    assert body, f"{asset} servi vide"


@pytest.mark.parametrize("token", [None, "", "mauvais-jeton"])
def test_the_journal_still_refuses_the_network_without_the_right_token(from_the_network, token):
    status, _ = _fetch(from_the_network, "/api/notice", token)
    assert status == HTTPStatus.UNAUTHORIZED


def test_the_journal_opens_to_the_network_with_the_right_token(from_the_network):
    status, body = _fetch(from_the_network, "/api/notice", TOKEN)
    assert status == HTTPStatus.OK
    assert json.loads(body)["headline"].startswith("Notice.")


@pytest.mark.parametrize("asset", ["/", "/app.css", "/app.js", "/manifest.webmanifest",
                                   "/icon-180.png", "/sw.js"])
def test_nothing_served_without_the_token_carries_a_decision(from_the_network, asset):
    """La contre-vérification, et la condition de toute la correction.

    Servir la coquille sans jeton n'est acceptable que tant qu'elle ne contient
    rien. Le jour où l'un de ces fichiers porterait une décision -- une page
    rendue côté serveur, un état préchargé pour aller plus vite -- ce choix
    deviendrait une fuite du journal vers tout le wifi, sans que rien
    n'échoue. Ce test l'interdit maintenant plutôt qu'après.
    """
    _, body = _fetch(from_the_network, asset)
    text = body.decode("utf-8", "replace")
    for marker in ("MARQUEUR-TITRE", "MARQUEUR-PREDIT", "MARQUEUR-LECON", "DEC-"):
        assert marker not in text, (
            f"{asset} contient {marker!r} et se sert sans jeton : le journal fuirait "
            "vers tout le réseau local.")


# --- pouvoir donner sa clé, plutôt que buter dessus --------------------------

def test_the_manifest_pins_no_start_url(from_the_network):
    """Un point d'entrée figé perdait la clé à l'installation.

    « Sur l'écran d'accueil » enregistre l'adresse d'où l'on part. Avec un
    `start_url` dans le manifeste, iOS l'utilise à la place, et il ne peut pas
    porter de clé — la mettre là la publierait, puisque le manifeste se sert
    sans authentification. Sans `start_url`, l'adresse retenue est celle qui
    est ouverte, jeton compris.
    """
    _, body = _fetch(from_the_network, "/manifest.webmanifest")
    manifest = json.loads(body)
    assert "start_url" not in manifest
    assert manifest["display"] == "standalone", "l'app doit rester en plein écran"


def test_the_page_offers_a_way_in_when_the_token_is_missing(from_the_network):
    """Un refus doit laisser un recours.

    L'app ajoutée à l'écran d'accueil a son propre stockage, séparé de Safari :
    elle démarre sans rien savoir, et n'affichait que « jeton d'accès manquant
    ou invalide ». Sans champ pour en fournir un, il n'y avait aucun geste
    possible depuis le téléphone.
    """
    _, body = _fetch(from_the_network, "/")
    page = body.decode("utf-8")
    for marker in ('id="unlock"', 'id="unlock-form"', 'id="unlock-input"'):
        assert marker in page, f"{marker} absent : un refus d'accès resterait sans issue"

    _, script = _fetch(from_the_network, "/app.js")
    code = script.decode("utf-8")
    assert "askForTheToken" in code
    assert "error.status === 401" in code, "le refus doit être reconnu par son statut"


# --- ce qu'une autre page peut demander en ton nom ---------------------------

def _post_as_a_page(base: str, path: str, payload: dict, **headers) -> int:
    """Poster comme le fait un navigateur pour le compte d'une page web.

    Aucun jeton : c'est le sujet. Une page n'en a pas besoin pour que le
    navigateur joigne à sa requête tout ce que la machine porte déjà.
    """
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as refused:
        return refused.code


A_DECISION = {"title": "écrit sans toi", "action": "rien", "predicted": "rien",
              "probability": 0.5, "cost_hours": 1, "tier": "REVENUS", "horizon_days": 7}


def test_another_page_cannot_write_to_the_journal(running, journal):
    """La faille telle qu'elle a été reproduite avant d'être corrigée.

    Le jeton dit qui sait ; il ne dit pas qui demande. Une page web ouverte sur
    cette machine parle depuis `127.0.0.1`, à qui la garde accordait tout parce
    qu'il n'y a « personne d'autre » sur la boucle locale. Il y a le navigateur.
    """
    assert _post_as_a_page(running, "/api/entries", A_DECISION,
                           Origin="https://site-malveillant.example") == HTTPStatus.FORBIDDEN
    assert not journal.entries(), "une page quelconque a écrit dans le journal"


def test_another_page_cannot_deliver_a_verdict_in_your_place(journal, running):
    """Le pire des deux : pas l'écriture, le verdict.

    Une décision tranchée par quelqu'un d'autre fausse le score de Brier, donc
    la calibration, qui est tout l'intérêt de l'outil. Et c'est l'invariant du
    projet pris à revers : le Sage ne décide pas à ta place, mais un site
    quelconque le faisait.
    """
    entry = journal.add(title="Postuler", action="envoyer", predicted="un entretien",
                        probability=0.75, tier=Tier.REVENUS, cost_hours=4, horizon_days=14)
    status = _post_as_a_page(running, f"/api/entries/{entry.entry_id}/resolve",
                             {"happened": False}, Origin="https://site-malveillant.example")
    assert status == HTTPStatus.FORBIDDEN
    assert journal.entries()[0].status is not Status.DID_NOT_HAPPEN, (
        "un verdict a été rendu à ta place"
    )


def test_a_page_without_an_origin_of_its_own_is_refused(running):
    """`null` est ce qu'annonce une page sandboxée ou ouverte depuis un fichier."""
    assert _post_as_a_page(running, "/api/entries", A_DECISION,
                           Origin="null") == HTTPStatus.FORBIDDEN


def test_a_body_a_page_could_send_without_asking_first_is_refused(running):
    """Le type du corps est la seconde barrière, indépendante de l'origine.

    Un navigateur n'envoie une requête vers une autre origine sans permission
    préalable que pour `text/plain`, un formulaire ou du multipart. Un
    formulaire HTML ne peut rien poster d'autre : le refus tient même si
    l'origine venait à manquer.
    """
    request = urllib.request.Request(
        running + "/api/entries", data=json.dumps(A_DECISION).encode(), method="POST",
        headers={"Content-Type": "text/plain;charset=UTF-8"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            code = response.status
    except urllib.error.HTTPError as refused:
        code = refused.code
    assert code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_a_domain_pointed_at_this_machine_is_refused(running):
    """Comparer l'origine à l'hôte ne suffit pas : il faut que l'hôte soit une adresse.

    Un attaquant qui fait pointer son domaine vers cette machine et sert sa page
    sur le même port obtient une origine et un hôte identiques. La comparaison
    dirait « même origine » pour une page qui est la sienne.
    """
    port = running.rsplit(":", 1)[1]
    assert _post_as_a_page(running, "/api/entries", A_DECISION,
                           Host=f"evil.example:{port}",
                           Origin=f"http://evil.example:{port}") == HTTPStatus.FORBIDDEN


def test_the_app_itself_still_writes(running, journal):
    """La garde ne vaut rien si elle ferme aussi la porte à l'app."""
    port = running.rsplit(":", 1)[1]
    request = urllib.request.Request(
        running + "/api/entries", data=json.dumps(A_DECISION).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Sage-Token": TOKEN,
                 "Origin": f"http://127.0.0.1:{port}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == HTTPStatus.OK
    assert len(journal.entries()) == 1


def test_a_client_that_is_not_a_browser_still_writes(running, journal):
    """`curl` et l'app native n'envoient pas d'origine, et ne portent pas de session."""
    assert _post_as_a_page(running, "/api/entries", A_DECISION) == HTTPStatus.OK
    assert len(journal.entries()) == 1


@pytest.mark.parametrize("host,accepted", [
    ("127.0.0.1:8765", True),
    ("192.168.1.20:8765", True),
    ("localhost:8765", True),
    ("[::1]:8765", True),
    ("::1", True),
    ("sage.local:8765", False),
    ("evil.example", False),
    ("", False),
])
def test_only_an_address_names_this_server(host: str, accepted: bool):
    assert host_is_an_address(host) is accepted


@pytest.mark.parametrize("origin,host,accepted", [
    ("", "127.0.0.1:8765", True),
    ("http://127.0.0.1:8765", "127.0.0.1:8765", True),
    ("http://127.0.0.1:8765", "127.0.0.1:9999", False),
    ("https://127.0.0.1:8765", "127.0.0.1:8765", False),
    ("null", "127.0.0.1:8765", False),
    ("http://evil.example", "127.0.0.1:8765", False),
])
def test_the_declared_origin_must_be_this_server(origin: str, host: str, accepted: bool):
    assert same_origin(origin, host) is accepted
