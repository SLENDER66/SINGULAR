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


# --- rien d'utile ne tombe hors du bloc qu'il colle ---------------------------

def test_le_bloc_a_deux_traits_et_rien_apres() -> None:
    """« Colle uniquement le bloc entre les deux traits » — encore faut-il qu'il
    contienne tout.

    La section « Ce que je dois faire moi-même » était écrite **après** le
    second trait. Elle n'était donc jamais collée : elle existait pour un
    lecteur du dépôt, et le dépôt, Claude le lit déjà tout seul. C'est le piège
    de la forme — une session qui ajoute une section à la fin d'un fichier
    l'ajoute hors de ce qui voyage.
    """
    lignes = PROMPT.read_text(encoding="utf-8").splitlines()
    traits = [numero for numero, ligne in enumerate(lignes) if ligne.strip() == "---"]

    assert len(traits) == 2, (
        f"{len(traits)} trait(s) au lieu de deux : le début et la fin du bloc à "
        "coller ne sont plus repérables.")

    apres = [ligne for ligne in lignes[traits[1] + 1:] if ligne.strip()]
    assert not apres, (
        "ces lignes sont après le second trait, donc jamais collées :\n  "
        + "\n  ".join(apres[:5])
        + "\n  Remonte-les avant le trait, ou retire-les.")


def test_la_commande_de_copie_extrait_bien_le_bloc() -> None:
    """La commande donnée en tête doit rendre exactement ce qui est entre les traits.

    Elle est écrite en `sed` dans un document, donc invérifiable à la lecture :
    une commande fausse donnerait un bloc tronqué, et un prompt tronqué se
    remarque tard -- après que la session a travaillé sur un mandat partiel.
    Ce test rejoue le découpage en Python et compare.
    """
    lignes = PROMPT.read_text(encoding="utf-8").splitlines()
    traits = [numero for numero, ligne in enumerate(lignes) if ligne.strip() == "---"]
    attendu = "\n".join(lignes[traits[0] + 1:traits[1]]).strip()

    entete = "\n".join(lignes[:traits[0]])
    assert entete.count("pbcopy") == 2, (
        "il faut les deux commandes de copie : celle qui marche sans clone, et "
        "celle du dépôt cloné. La première a été écrite en supposant un clone "
        "qu'il n'avait pas.")
    assert entete.count("sed -n '/^---$/,/^---$/p'") == 2, "le découpage n'est plus celui-ci"
    assert entete.count("sed '1d;$d'") == 2, "les deux traits eux-mêmes doivent être retirés"
    assert "raw.githubusercontent.com" in entete, (
        "la commande sans clone a disparu : c'est la seule qui marche sur une "
        "machine neuve, et c'est le cas qui s'est presenté")

    # Ce que la commande produirait, rejoué ici.
    debut = next(i for i, ligne in enumerate(lignes) if ligne.strip() == "---")
    fin = next(i for i, ligne in enumerate(lignes[debut + 1:], start=debut + 1)
               if ligne.strip() == "---")
    produit = "\n".join(lignes[debut + 1:fin]).strip()
    assert produit == attendu
    assert "POUR QUI TU TRAVAILLES" in produit, "les règles doivent être dans le bloc"
    assert "Ce que je dois faire moi-même" in produit, "et la dernière section aussi"


def test_l_adresse_brute_nomme_la_branche_de_travail() -> None:
    """Une URL brute pointe une branche, et la mauvaise donnerait un mandat perime.

    C'est le meme defaut que le `git clone` sans `-b`, a un endroit que le
    garde-fou des clones ne voit pas : ce n'est pas une commande de clonage.
    """
    import sys

    sys.path.insert(0, str(RACINE / "tools"))
    try:
        from check_repo_state import declared_work_branch
    finally:
        sys.path.pop(0)

    travail = declared_work_branch((RACINE / "CLAUDE.md").read_text(encoding="utf-8"))
    entete = PROMPT.read_text(encoding="utf-8").split("\n---\n")[0]
    # Le nom de branche contient une barre oblique : s'arreter a la premiere
    # rendait « claude ». Le fichier vise sert de borne.
    adresses = re.findall(
        r"raw\.githubusercontent\.com/[^/]+/[^/]+/(.+?)/PROMPT_NOUVELLE_CONVERSATION\.md",
        entete)

    assert adresses, "plus aucune adresse brute dans l'en-tete"
    for branche in adresses:
        assert branche == travail, (
            f"l'adresse brute pointe « {branche} », le mandat declare « {travail} » : "
            "il collerait un prompt d'une autre branche")


# --- le bloc ne contredit pas le code qu'il decrit ----------------------------

def test_le_bloc_ne_promet_pas_une_dette_de_vecteurs_qui_n_existe_plus() -> None:
    """Il annoncait un `Cmd + U` rouge comme normal. Il ne l'est plus.

    Pendant des semaines, les vecteurs committes exigeaient du port Swift deux
    observations qu'il ne produit pas : l'ecart etait declare d'un cote et
    contredit de l'autre. Corrige le 9 septembre 2026 -- le generateur refuse
    d'ecrire un tel vecteur. Le bloc, lui, disait encore « le premier Mac qui
    compilera verra ces vecteurs echouer », ce qui ferait prendre un vrai
    defaut pour une dette connue le jour ou il compile.
    """
    generateur = (RACINE / "tools" / "generate_notice_vectors.py").read_text(encoding="utf-8")
    assert "_refuse_les_absentes" in generateur, (
        "le garde-fou du generateur a disparu : cette regle ne garde plus rien")

    texte = PROMPT.read_text(encoding="utf-8")
    for promesse in ("vecteurs committés les attendent",
                     "verra ces vecteurs échouer",
                     "vecteurs committes les attendent"):
        assert promesse not in texte, (
            f"le bloc annonce « {promesse} » alors que le generateur refuse "
            "desormais d'ecrire un vecteur qui declenche une observation absente "
            "du port. Un Cmd+U rouge est un vrai defaut.")


def test_le_bloc_ne_classe_pas_un_genre_d_offre_avant_l_autre() -> None:
    """« Postes et alternances, sans hierarchie » -- sa reponse du 9 septembre.

    Le bloc disait « chercher un poste classique passe devant », et la faculte
    `offres` classait l'alternance en second. Les deux venaient d'une deduction
    que personne ne lui avait demande de confirmer, et c'est la classe de faute
    qui lui a deja coute un CV faux et un marche ecarte.
    """
    faculte = (RACINE / "singular" / "offres.py").read_text(encoding="utf-8")
    assert "sans mettre un genre avant" in faculte, (
        "la faculte `offres` ne dit plus de couvrir les deux sans hierarchie : "
        "verifie laquelle des deux sources a change avant de corriger l'autre")

    texte = PROMPT.read_text(encoding="utf-8")
    assert "sans hiérarchie" in texte, (
        "le bloc ne porte plus sa reponse du 9 septembre. Un lecteur qui ne la "
        "trouve pas la rededuira, et la deduction precedente lui a coute un CV "
        "faux et un marche ecarte.")

    # On verifie ce que le bloc affirme, pas ce qu'il evite de dire. Chercher
    # « poste classique passe devant » accusait deux phrases : celle qui cite
    # l'ancienne formulation pour la corriger, et « aucune ne passe devant
    # l'autre » a propos des deux CV. Un test qui crie au loup finit desactive,
    # et c'est la troisieme fois aujourd'hui que la forme substring le fait.
    assert "poste et alternance" in texte or "postes et alternances" in texte


def test_le_bloc_ne_laisse_pas_recoller_deux_journaux() -> None:
    """La faute la plus couteuse qu'une prochaine session puisse lui proposer.

    Son journal est sur une machine hors de portee, il ecrit sur l'autre en
    attendant, et les deux devront se rejoindre. Recoller deux bases ligne a
    ligne rompt la chaine pour toujours -- mesure dans
    `tests/test_deux_journaux.py`. Une session qui ne le sait pas proposera
    exactement ca : c'est le geste evident.

    Le bloc doit donc porter la commande qui le fait proprement, et l'avertir.
    """
    depot = (RACINE / "singular" / "journal.py").read_text(encoding="utf-8")
    assert "def import_from" in depot, (
        "la reprise a disparu du journal : le conseil du bloc n'a plus d'objet")

    texte = PROMPT.read_text(encoding="utf-8")
    assert "singular import" in texte, (
        "le bloc ne nomme pas `import` : la prochaine session proposera de "
        "recopier des lignes d'une base dans l'autre, ce qui rompt la chaine")
    assert "recopier des lignes" in texte, "et l'avertissement doit y etre aussi"
