"""Le Sage doit tourner sans moi.

`test_sage_isolation.py` interdit au Sage d'agir sur le monde. Ce fichier
interdit l'inverse : que le monde lui devienne nécessaire.

La raison n'est pas technique. Un outil qui accompagne une vie ne peut pas
dépendre d'un abonnement qu'on peut résilier, d'une clé qu'on peut révoquer,
d'un service qui peut fermer, ni d'un réseau qui peut tomber. Le journal, la
chaîne d'intégrité, la Notice et la calibration doivent fonctionner sur une
machine débranchée, dans dix ans, sans que personne ait à payer quoi que ce
soit — sinon ce n'est pas un outil, c'est une location.

L'analyse en langage naturel viendra, et elle consommera une clé d'API. Elle
devra pouvoir être coupée sans rien emporter avec elle. Ces tests sont ce qui
rend cette séparation vérifiable plutôt que promise.
"""
from __future__ import annotations

import ast
import builtins
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
#: Le cœur déterministe : ce qui doit marcher débranché, pour toujours.
DETERMINISTIC = [ROOT / "singular" / "sage", ROOT / "singular" / "journal.py"]

#: Les bibliothèques qui parlent à un service distant, ou à un modèle.
REACHES_OUT = frozenset({
    "anthropic", "openai", "google", "genai", "mistralai", "cohere", "ollama",
    "requests", "httpx", "aiohttp", "urllib3", "boto3", "botocore",
    "langchain", "llama_index", "transformers", "torch", "tiktoken",
})

#: Ce qu'une clé d'accès s'appelle, quel que soit le fournisseur.
LOOKS_LIKE_A_KEY = ("API_KEY", "APIKEY", "SECRET_KEY", "ACCESS_TOKEN", "AUTH_TOKEN")


def _sources() -> list[Path]:
    found: list[Path] = []
    for target in DETERMINISTIC:
        found.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target])
    return found


def test_the_deterministic_core_imports_nothing_that_calls_a_service() -> None:
    checked = 0
    for source in _sources():
        checked += 1
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = imported & REACHES_OUT
        assert not forbidden, (
            f"{source.relative_to(ROOT)} importe {sorted(forbidden)}. Le cœur du Sage doit "
            "tourner sur une machine débranchée : une faculté qui appelle un service vit "
            "ailleurs, derrière une frontière qu'on peut couper."
        )
    assert checked >= 5, "le test doit voir les modules du cœur, pas un dossier vide"


def test_the_deterministic_core_reads_no_access_key() -> None:
    """Aucune clé lue, donc aucune clé à fournir, donc rien à payer."""
    for source in _sources():
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            named = node.value.upper()
            assert not any(marker in named for marker in LOOKS_LIKE_A_KEY), (
                f"{source.relative_to(ROOT)}:{node.lineno} nomme {node.value!r}. "
                "Le journal et la Notice ne doivent rien avoir à authentifier.")


def test_the_notice_is_built_with_the_network_removed(tmp_path, monkeypatch) -> None:
    """La preuve par l'acte : on retire les sockets, tout doit marcher.

    Un test d'imports montre qu'aucune bibliothèque réseau n'est chargée. Il ne
    montre pas qu'aucun appel n'est fait — la bibliothèque standard sait
    ouvrir une connexion sans qu'on importe rien de particulier. Ici on rend la
    chose impossible et on refait le parcours complet : écrire, trancher,
    vérifier la chaîne, produire la Notice.
    """
    from singular.journal import DecisionJournal, Tier
    from singular.sage import build_notice

    now = datetime(2026, 9, 6, 9, 0, tzinfo=UTC)
    journal = DecisionJournal(tmp_path / "journal.db")

    def refuse(*args, **kwargs):
        raise AssertionError("le cœur du Sage a tenté d'ouvrir une connexion")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    first = journal.add(title="Postuler", action="candidature", predicted="un entretien",
                        probability=0.4, tier=Tier.REVENUS, cost_hours=3, horizon_days=14, now=now)
    journal.add(title="Loyer", action="virement", predicted="bail signé", probability=0.9,
                tier=Tier.STABILITE, cost_hours=1, horizon_days=30, now=now)
    journal.resolve(first.entry_id, happened=False, now=now + timedelta(days=14))

    assert journal.verify() is True
    notice = build_notice(journal, now=now + timedelta(days=20))
    assert notice.headline.startswith("Notice.")
    assert notice.report["decisions"] == 2
    assert notice.items, "une Notice sans observation ne prouverait rien"


def test_the_network_guard_would_actually_catch_a_connection(monkeypatch) -> None:
    """Le témoin : sans lui, le test ci-dessus passerait même s'il ne bloquait rien."""
    def refuse(*args, **kwargs):
        raise AssertionError("connexion tentée")

    monkeypatch.setattr(socket, "create_connection", refuse)
    with pytest.raises(AssertionError, match="connexion tentée"):
        socket.create_connection(("example.invalid", 80))


def test_the_deterministic_core_needs_nothing_installed() -> None:
    """Pas de `pip install` entre l'utilisateur et son journal.

    Le dépôt a des dépendances de développement — pytest, ruff, mypy. Le cœur,
    lui, doit s'exécuter sur un Python nu : c'est ce qui permet de lancer le
    Sage sur un PC où rien n'a été préparé.
    """
    import sys

    standard = set(sys.stdlib_module_names) | {"singular"}
    for source in _sources():
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: set[str] = set()
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = {node.module.split(".")[0]}
            outside = names - standard - set(dir(builtins))
            assert not outside, (
                f"{source.relative_to(ROOT)} dépend de {sorted(outside)}, hors bibliothèque "
                "standard : lancer le Sage exigerait une installation de plus.")
