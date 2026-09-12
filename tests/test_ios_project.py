"""Le projet Xcode doit rester ouvrable et complet.

Personne ici n'a Xcode : ce projet est écrit à la main et poussé sans avoir
jamais été ouvert. La panne qu'on veut exclure n'est pas subtile — c'est
« the project is damaged and cannot be opened », qui bloque la personne qui
compile avant même la première erreur Swift, et sans rien lui apprendre.

Le vrai risque n'est pas le fichier d'aujourd'hui, qui a été vérifié : c'est
celui de demain. Ajouter un fichier Swift sans le déclarer dans le projet le
laisserait hors de la compilation, et le symptôme serait « type inconnu » dans
un fichier qui, lui, est correct. Ce test attache cette vérification à la
suite, pour qu'elle tourne sans qu'on y pense.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
CHECKER = RACINE / "tools/check_xcode_project.py"


def test_the_xcode_project_opens_and_is_complete() -> None:
    result = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
    assert result.returncode == 0, (
        "le projet Xcode ne tient plus :\n" + result.stdout + result.stderr)


def test_the_checker_refuses_a_damaged_project(tmp_path: pathlib.Path) -> None:
    """Un vérificateur qui ne dit jamais non ne prouve rien.

    On lui donne un projet dont il ne reste que l'en-tête : il doit refuser.
    Sans ce cas, une régression qui ferait passer le vérificateur en mode
    « tout va bien quoi qu'il arrive » ne se verrait nulle part.
    """
    source = CHECKER.read_text()
    damaged = tmp_path / "SingularSage.xcodeproj"
    damaged.mkdir(parents=True)
    (damaged / "project.pbxproj").write_text("// !$*UTF8*$!\n{ objectVersion = 56")

    copy = tmp_path / "check.py"
    copy.write_text(source.replace(
        'PROJECT = pathlib.Path(__file__).resolve().parent.parent / "ios/SingularSage.xcodeproj/project.pbxproj"',
        f'PROJECT = pathlib.Path({str(damaged / "project.pbxproj")!r})'))

    result = subprocess.run([sys.executable, str(copy)], capture_output=True, text=True)
    assert result.returncode == 1, "un projet tronqué doit être refusé"
    assert "damaged" in result.stdout


# --- ce que le code exige vraiment, et ce que le projet demande ----------------

def test_la_cible_ios_est_plus_haute_que_ce_que_le_code_exige() -> None:
    """Le constat du 10 septembre 2026, garde parce qu'il decide de tout.

    L'App Store a refuse Xcode sur son Mac. Le premier levier serait d'abaisser
    la cible : le projet declare iOS 17, et rien dans les sources n'en a besoin.
    Le plancher reel est `NavigationStack`, donc iOS 16.

    Il a ecarte l'app native le meme jour, donc rien n'a ete change. Ce test ne
    force pas la cible : il refuse que le constat vieillisse en silence. Le jour
    ou une API iOS 17 entre dans les sources, la note d'`ios/README.md` devient
    fausse et c'est ici qu'on l'apprend.
    """
    sources = " ".join(chemin.read_text(encoding="utf-8")
                       for chemin in sorted((RACINE / "ios").rglob("*.swift")))
    seulement_ios_17 = ("@Observable", "ContentUnavailableView", "scrollTargetBehavior",
                        "symbolEffect", "PhaseAnimator", "containerRelativeFrame",
                        "ScrollView(.vertical, showsIndicators")
    trouvees = [nom for nom in seulement_ios_17 if nom in sources]

    assert not trouvees, (
        f"les sources utilisent maintenant {trouvees}, qui demandent iOS 17. "
        "`ios/README.md` et `A_FAIRE.md` affirment que le plancher reel est "
        "iOS 16 : corrige-les, ou retire l'API.")
    assert "NavigationStack" in sources, (
        "`NavigationStack` a disparu : le plancher reel n'est peut-etre plus "
        "iOS 16, et les deux documents qui l'annoncent sont a relire.")


def test_les_documents_disent_que_l_app_native_est_ecartee() -> None:
    """Une porte fermee doit se lire comme fermee, sinon on la repousse.

    Une session a deja perdu son temps a reparer ce port pendant que l'app web
    dormait, finie, dans le meme depot. Il l'a ecarte lui-meme le 10 septembre ;
    si les documents continuent de la presenter comme une tache en attente, la
    prochaine session recommencera.
    """
    for nom in ("ios/README.md", "A_FAIRE.md", "PROMPT_NOUVELLE_CONVERSATION.md"):
        # Replie a la main, et parfois en citation : « ce n'est pas une\n>
        # tache en attente ». Chercher la phrase telle quelle rate exactement le
        # document ou elle est le mieux mise en valeur. Meme piege que
        # `test_docs_sans_compte_perissable.py`, qui le documente deja.
        texte = re.sub(r"\s*\n>?\s*", " ", (RACINE / nom).read_text(encoding="utf-8"))
        assert "carté" in texte or "cartée" in texte or "mise de côté" in texte, (
            f"{nom} ne dit pas que l'app native est ecartee")
        assert "pas une tâche en attente" in texte or "Ne me la repropose pas" in texte, (
            f"{nom} la laisse passer pour du travail qui attend")
