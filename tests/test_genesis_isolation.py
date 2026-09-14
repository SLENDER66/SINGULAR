"""Genesis réfléchit ; elle n'agit pas, et elle ne coûte rien.

Le mandat pose une séparation avant tout le reste : INTELLIGENCE ≠ DECISION ≠
AUTHORIZATION ≠ EXECUTION. Un paquet qui planifie des missions, construit des
capacités et les inscrit dans un registre est précisément le genre de chose qui
obtient un pouvoir d'exécution sans que personne ne le lui ait donné — il suffit
d'un import, un jour, pour une bonne raison.

Ce fichier refuse cet import plutôt que de compter dessus. C'est le pendant de
`test_sage_isolation.py` pour le Sage, et la même raison : le dépôt a une
frontière d'exécution, et rien n'a le droit d'en devenir une porte de service.

Il tient aussi l'autre bord. Genesis ne doit dépendre d'aucun modèle, d'aucune
clé, d'aucun réseau : une expérience qui ne tourne qu'avec cinq dollars de
crédit est une expérience que le CI ne rejouera jamais, et qui finira comme
l'application web finie et jamais lancée dont le mandat garde le souvenir.
"""
from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
GENESIS = RACINE / "singular" / "genesis"

#: Tout ce qui, dans ce dépôt, peut finir par changer quelque chose dans le
#: monde. Genesis n'en importe aucun.
CE_QUI_EXECUTE = frozenset({
    "execution", "durable_execution", "reconciled_execution", "validated_execution",
    "validated_pipeline", "validated_decision_service", "effects", "providers",
    "tool_fabric", "autopilot", "mission_autopilot", "mission_runtime", "control_plane",
    "production_runtime", "decision_attestation", "durable", "store", "engine",
    "v3_operating_system", "v32_governed_core", "empire", "agents", "collecte",
    "saisie", "fichiers", "offres", "parle", "analyse",
})

#: La seule exception, et elle est nommée, pas devinée. `artifact_fingerprint`
#: est une fonction pure : elle calcule l'identité d'un objet appelable et ne
#: peut rien exécuter. La directive interdit de dupliquer ce qui existe, et
#: réécrire une deuxième empreinte d'artefact à côté de celle que la frontière
#: utilise serait la garantie qu'elles divergent.
EXCEPTION = ("execution_capability", frozenset({"artifact_fingerprint"}))

#: Les bibliothèques qui parlent à un service distant, ou à un modèle.
APPELLE_DEHORS = frozenset({
    "anthropic", "openai", "google", "genai", "mistralai", "cohere", "ollama",
    "requests", "httpx", "aiohttp", "urllib3", "urllib", "boto3", "botocore", "socket",
    "langchain", "llama_index", "transformers", "torch", "tiktoken", "http",
})

#: Ce qui écrit, supprime ou lance un processus.
CE_QUI_ECRIT = ("write_text", "write_bytes", "mkdir", "unlink", "rmtree", "remove",
                "popen", "system", "run", "check_call", "check_output", "Popen")


def _sources() -> list[Path]:
    trouve = sorted(GENESIS.rglob("*.py"))
    assert len(trouve) >= 5, "le test doit voir les modules de Genesis, pas un dossier vide"
    return trouve


def test_genesis_n_importe_rien_qui_puisse_executer() -> None:
    """Un chemin vers la frontière, c'est un contournement de la frontière."""
    module_exception, noms_permis = EXCEPTION
    for source in _sources():
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    dernier = alias.name.split(".")[-1]
                    assert dernier not in CE_QUI_EXECUTE and dernier != module_exception, (
                        f"{source.relative_to(RACINE)} importe {alias.name} : Genesis "
                        "réfléchit, elle n'exécute pas")
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                dernier = noeud.module.split(".")[-1]
                if dernier == module_exception:
                    demandes = {alias.name for alias in noeud.names}
                    assert demandes <= noms_permis, (
                        f"{source.relative_to(RACINE)} prend {sorted(demandes - noms_permis)} "
                        f"dans {noeud.module} : seul {sorted(noms_permis)} est permis, "
                        "parce que c'est une fonction pure")
                    continue
                assert dernier not in CE_QUI_EXECUTE, (
                    f"{source.relative_to(RACINE)} importe depuis {noeud.module} : "
                    "Genesis réfléchit, elle n'exécute pas")


def test_genesis_n_appelle_aucun_service() -> None:
    """Ni modèle, ni clé, ni réseau : le banc doit tourner dans le CI, gratuitement."""
    for source in _sources():
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        importe: set[str] = set()
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                importe |= {alias.name.split(".")[0] for alias in noeud.names}
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                importe.add(noeud.module.split(".")[0])
        interdits = importe & APPELLE_DEHORS
        assert not interdits, (
            f"{source.relative_to(RACINE)} importe {sorted(interdits)} : une mission "
            "Genesis doit pouvoir tourner sur une machine débranchée")


def test_genesis_n_ecrit_nulle_part() -> None:
    """Une mission lit. Rien dans ce paquet n'a de raison d'écrire sur le disque."""
    for source in _sources():
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute):
                assert noeud.func.attr not in CE_QUI_ECRIT, (
                    f"{source.relative_to(RACINE)}:{noeud.lineno} appelle "
                    f"{noeud.func.attr}() : Genesis lit, elle n'écrit pas")
            if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) \
                    and noeud.func.id == "open":
                mode = next((mot.value.value for mot in noeud.keywords
                             if mot.arg == "mode" and isinstance(mot.value, ast.Constant)), "r")
                positionnel = (noeud.args[1].value
                               if len(noeud.args) > 1 and isinstance(noeud.args[1], ast.Constant)
                               else "r")
                assert "w" not in str(mode) + str(positionnel) \
                    and "a" not in str(mode) + str(positionnel), (
                    f"{source.relative_to(RACINE)}:{noeud.lineno} ouvre un fichier en écriture")


def test_les_trois_missions_tournent_le_reseau_coupe(monkeypatch) -> None:
    """La preuve par l'acte, comme pour le Sage : on retire les sockets.

    Un test d'imports montre qu'aucune bibliothèque réseau n'est chargée. Il ne
    montre pas qu'aucun appel n'est fait -- la bibliothèque standard sait ouvrir
    une connexion sans qu'on importe rien de particulier.
    """
    from singular.genesis import Registre, Trajectoire, executer
    from singular.genesis.missions import (GAMMA_APPRENTISSAGE, alpha, apprendre_de_gamma,
                                           beta, gamma, resoudre, sources_du_depot)

    sources = sources_du_depot(RACINE)

    def refuse(*args, **kwargs):
        raise AssertionError("Genesis a tenté d'ouvrir une connexion")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    registre = Registre()
    for mission in (alpha(sources), beta(sources)):
        assert executer(mission, lambda m, t: resoudre(m, t, registre)).verifie, mission.nom

    assert apprendre_de_gamma(registre, Trajectoire("acquisition"))
    apres = executer(gamma(GAMMA_APPRENTISSAGE), lambda m, t: resoudre(m, t, registre))
    assert apres.verifie


def test_le_garde_reseau_attraperait_vraiment_une_connexion(monkeypatch) -> None:
    """Le témoin : sans lui, le test du dessus passerait même s'il ne bloquait rien."""
    def refuse(*args, **kwargs):
        raise AssertionError("connexion tentée")

    monkeypatch.setattr(socket, "create_connection", refuse)
    with pytest.raises(AssertionError, match="connexion tentée"):
        socket.create_connection(("example.invalid", 80))


def test_genesis_se_retire_sans_rien_emporter() -> None:
    """Le protocole d'arrêt de la directive, dans sa forme la plus simple.

    Toute évolution importante doit pouvoir être désactivée. Ici, ça veut dire
    qu'on peut supprimer `singular/genesis/` et que le reste du dépôt continue :
    rien dans `singular/` ne l'importe. `docs/AZAZEL_GENESIS.md` l'affirme, donc
    ce test existe -- une garantie sans test est une intention.
    """
    fautifs = []
    for source in (RACINE / "singular").rglob("*.py"):
        if GENESIS in source.parents:
            continue
        arbre = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for noeud in ast.walk(arbre):
            cible = ""
            if isinstance(noeud, ast.Import):
                cible = " ".join(alias.name for alias in noeud.names)
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                cible = noeud.module
            if "genesis" in cible:
                fautifs.append(f"{source.relative_to(RACINE)}:{noeud.lineno}")
    assert not fautifs, (
        f"{fautifs} importe(nt) Genesis : le paquet ne serait plus supprimable, "
        "et l'expérience deviendrait une dépendance de l'outil")
