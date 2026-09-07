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


def test_the_hours_figure_waits_for_a_verdict_before_warning() -> None:
    """Le chiffre doit s'alarmer aux mêmes conditions que la phrase.

    L'observation « Xh engagées sans verdict » attend qu'un verdict existe :
    reprocher de ne pas avoir tranché ce dont l'échéance n'est pas venue est
    faux. La vignette voisine portait toujours l'ancienne règle et s'allumait
    en doré dès la première décision — la même accusation, en plus discrète.

    Ce test lit le source plutôt que d'exécuter le rendu : l'affichage demande
    un DOM, que ce dépôt n'a pas. Il tient donc la condition, pas le pixel.
    """
    code = CLIENT.read_text(encoding="utf-8")
    marker = 'figure(`${report.hours_unresolved}h`, "encore sans verdict",'
    assert marker in code, "la vignette a changé de forme : ce test ne la voit plus"
    condition = code.split(marker, 1)[1].split("),", 1)[0]
    assert "report.resolved > 0" in condition, (
        "la vignette s'alarmerait avant qu'un verdict ait pu être rendu")


#: Le bloc du verdict, decoupe entre son verrou et la section suivante.
def _bloc_verdict() -> str:
    code = CLIENT.read_text(encoding="utf-8")
    debut = code.index("let verdictEnCours")
    fin = code.index("// --- démarrage", debut)
    return code[debut:fin]


def _executer(scenario: str) -> dict:
    """Joue le bloc du verdict dans node, avec un DOM et un reseau simules."""
    harness = """
    const appels = [];
    const erreurs = [];
    const boutons = {"resolve-yes": {disabled: false}, "resolve-no": {disabled: false}};
    const $ = (id) => boutons[id] || {reset() {}, close() {}, textContent: "", hidden: true};
    class FormData { constructor() {} get() { return "une lecon"; } }
    let resolving = "DEC-1";
    let reponse = null;
    async function api(chemin, options) {
      appels.push(JSON.parse(options.body));
      await new Promise((r) => setTimeout(r, 20));
      if (reponse) throw reponse;
      return {};
    }
    async function refresh() {}
    function showFormError(id, message) { erreurs.push(message); }
    """ + _bloc_verdict() + scenario
    resultat = subprocess.run([NODE, "-e", harness], capture_output=True, text=True,
                              timeout=20, check=False)
    assert resultat.returncode == 0, resultat.stderr
    return json.loads(resultat.stdout)


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_un_double_appui_n_envoie_qu_un_seul_verdict() -> None:
    """Deux boutons cote a cote, et un serveur local qui met un instant.

    « Arrive » puis, sans reponse visible, « Pas arrive » : deux verdicts
    contradictoires partaient. Le journal refuse desormais la seconde
    ecriture, mais le message qui revenait etait le sien -- technique, en
    anglais, le matin ou l'on tranche.
    """
    resultat = _executer("""
    (async () => {
      const premier = submitResolve(true);
      submitResolve(false);          // le double appui, sans attendre
      await premier;
      process.stdout.write(JSON.stringify({appels, erreurs}));
    })();
    """)

    assert len(resultat["appels"]) == 1, f"{len(resultat['appels'])} verdicts envoyes"
    assert resultat["appels"][0]["happened"] is True
    assert resultat["erreurs"] == []


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_les_boutons_sont_reouverts_apres_l_envoi() -> None:
    """Sinon un echec reseau laisserait la decision intranchable."""
    resultat = _executer("""
    (async () => {
      await submitResolve(true);
      process.stdout.write(JSON.stringify({
        verrouilles: [boutons["resolve-yes"].disabled, boutons["resolve-no"].disabled],
      }));
    })();
    """)

    assert resultat["verrouilles"] == [False, False]


@pytest.mark.skipif(NODE is None, reason="node absent")
def test_un_conflit_se_lit_en_francais_et_ne_ressemble_pas_a_une_panne() -> None:
    """409 : l'autre appareil a tranche. Ce n'est pas une panne, et le message
    brut du journal -- « history is not editable » -- ne le dit pas."""
    resultat = _executer("""
    reponse = Object.assign(new Error("DEC-1 was already resolved as HAPPENED"), {status: 409});
    (async () => {
      await submitResolve(true);
      process.stdout.write(JSON.stringify({erreurs}));
    })();
    """)

    assert len(resultat["erreurs"]) == 1
    message = resultat["erreurs"][0]
    assert "déjà été tranchée" in message
    assert "history is not editable" not in message
