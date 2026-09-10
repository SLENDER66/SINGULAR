"""Le bloc qu'il colle en nouvelle conversation doit dire vrai.

`PROMPT_NOUVELLE_CONVERSATION.md` est le seul texte qui traverse d'une session
à l'autre par ses mains. Il porte deux choses fragiles.

**Les règles, recopiées en entier.** Il les a demandées ainsi le 10 septembre
2026 : les sections 0 et 24 du mandat, mot pour mot, pour qu'elles restent
lisibles quand il colle le bloc ailleurs que dans le dépôt. Une règle écrite à
deux endroits est le défaut que ce dépôt a payé neuf fois — la calibration, le
reproche des rangs fondateurs, le seuil de retard, la ligne d'en-tête de
l'export. La copie ne peut donc pas être laissée à la vigilance : elle se
compare caractère par caractère à son original.

**L'état de sa machine.** Le bloc a dit « je suis sur Windows, dans
PowerShell » jusqu'au jour où ce n'était plus vrai. Un prompt qui envoie la
prochaine session écrire du PowerShell pour un Mac est pire qu'un prompt vide :
il fait perdre l'aller-retour, et il le fait avec autorité.
"""
from __future__ import annotations

import pathlib
import re

RACINE = pathlib.Path(__file__).resolve().parent.parent
MANDAT = RACINE / "CLAUDE.md"
PROMPT = RACINE / "PROMPT_NOUVELLE_CONVERSATION.md"

#: Les sections du mandat que le bloc recopie, et ce qui les termine.
SECTIONS = {
    "0. POUR QUI TU TRAVAILLES": "1. TON RÔLE",
    "24. MODE DE COLLABORATION": "25. CE QUE TU DOIS FAIRE MAINTENANT",
}


def _section(titre: str, suivant: str) -> str:
    mandat = MANDAT.read_text(encoding="utf-8")
    assert titre in mandat, f"« {titre} » a disparu du mandat"
    bloc = mandat[mandat.index(titre):mandat.index(suivant)]
    return bloc.rstrip().removesuffix("⸻").rstrip()


def _blocs_recopies() -> list[str]:
    return [bloc.strip() for bloc in
            re.findall(r"```text\n(.*?)```", PROMPT.read_text(encoding="utf-8"), re.DOTALL)]


def test_les_regles_recopiees_sont_celles_du_mandat() -> None:
    recopies = _blocs_recopies()
    assert len(recopies) == len(SECTIONS), (
        f"{len(recopies)} bloc(s) de règles recopié(s) pour {len(SECTIONS)} section(s) "
        "du mandat : le prompt et le mandat ne parlent plus des mêmes règles")

    for (titre, suivant), recopie in zip(SECTIONS.items(), recopies):
        attendu = _section(titre, suivant).strip()
        assert recopie == attendu, (
            f"la copie de « {titre} » a divergé de `CLAUDE.md`.\n"
            "Regénère-la depuis le mandat : c'est le mandat qui fait foi, pas la copie.\n"
            f"  mandat : {attendu[:120]!r}\n"
            f"  copie  : {recopie[:120]!r}")


def test_le_temoin_lit_bien_quelque_chose() -> None:
    """Sans lui, un prompt vidé de ses blocs passerait au vert."""
    recopies = _blocs_recopies()
    assert recopies and all(len(bloc) > 500 for bloc in recopies)
    assert "POUR QUI TU TRAVAILLES" in recopies[0]
    assert "MODE DE COLLABORATION" in recopies[1]


# --- ce que le bloc dit de sa machine ----------------------------------------

#: Ce qui n'est plus vrai depuis le 10 septembre 2026.
PERIME = {
    r"\bje suis sur Windows\b": "il est sur Mac",
    r"\bmon PC Windows\b": "sa machine est un Mac",
    r"\bC:\\Users\\": "les chemins sont en ~/…",
    r"\$env:": "la variable se pose avec export",
    r"\bje n'ai pas de Mac\b": "il en a un depuis le 10 septembre 2026",
}


def test_le_prompt_ne_decrit_pas_une_machine_qu_il_n_a_plus() -> None:
    texte = PROMPT.read_text(encoding="utf-8")
    fautes = []
    for motif, verite in PERIME.items():
        for trouve in re.finditer(motif, texte, re.IGNORECASE):
            ligne = texte[:trouve.start()].count("\n") + 1
            fautes.append(f"ligne {ligne} : {trouve.group(0)!r} — {verite}")

    assert not fautes, (
        "le bloc collé en nouvelle conversation décrit une machine périmée :\n  "
        + "\n  ".join(fautes)
        + "\n  Il envoie la prochaine session écrire pour la mauvaise machine, "
        "avec autorité.")


def test_le_prompt_dit_de_quelle_machine_il_parle() -> None:
    """L'inverse : un prompt muet sur la machine laisse deviner, et on devine mal."""
    texte = PROMPT.read_text(encoding="utf-8")
    assert re.search(r"\bMac\b", texte), "le bloc ne nomme plus sa machine"
    assert "zsh" in texte, "ni son terminal"
