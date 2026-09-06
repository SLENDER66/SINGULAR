"""Le peu de logique du client qu'on peut exécuter ici.

Le navigateur n'est pas dans ce dépôt, et rien de ce qui suit ne remplace le
fait d'ouvrir l'app sur un téléphone. Mais la lecture de la clé collée est de
l'analyse de texte pure : elle s'exécute, donc elle se teste, et c'est le
point où l'utilisateur bloqué reprend la main.

Node n'est pas une dépendance du projet. Quand il manque, ces tests se
retirent plutôt que de faire semblant.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

CLIENT = pathlib.Path(__file__).resolve().parent.parent / "singular/sage/web/app.js"
NODE = shutil.which("node")

CASES = [
    ("http://192.168.1.71:8765/?k=BU2szrWJwJHpK", "BU2szrWJwJHpK"),
    ("http://192.168.1.71:8765/?k=abc&autre=1", "abc"),
    ("http://192.168.1.71:8765/?x=1&k=abc", "abc"),
    ("  http://10.0.0.4:8765/?k=avec-espaces  ", "avec-espaces"),
    ("BU2szrWJwJHpK", "BU2szrWJwJHpK"),
    ("  jeton-colle-seul  ", "jeton-colle-seul"),
    ("", ""),
    ("   ", ""),
    ("http://192.168.1.71:8765/?k=a%2Fb", "a/b"),
]


@pytest.mark.skipif(NODE is None, reason="node absent : le client ne peut pas être exécuté ici")
@pytest.mark.parametrize(("supplied", "expected"), CASES)
def test_a_pasted_address_or_a_bare_token_both_yield_the_key(supplied: str, expected: str) -> None:
    """L'utilisateur colle ce qu'il a sous la main, pas ce qu'on attend de lui."""
    harness = f"""
    {CLIENT.read_text(encoding="utf-8").split("async function api")[0]}
    process.stdout.write(JSON.stringify(readSuppliedToken({json.dumps(supplied)})));
    """
    result = subprocess.run([NODE, "-e", harness], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_the_client_still_parses() -> None:
    """Une erreur de syntaxe rendrait l'app blanche, sans message."""
    result = subprocess.run([NODE, "--check", str(CLIENT)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
