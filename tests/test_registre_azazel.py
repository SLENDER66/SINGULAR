"""Le registre qu'il a demandé doit atteindre le modèle, et ne pas déborder ailleurs.

La section 26 du mandat le nomme : souveraineté froide, aucun apitoiement, un
acte mesurable et daté à chaque échange — et **c'est lui qui le nomme**, jamais
la machine, parce qu'un acte imposé est encore une béquille.

Ce fichier ne juge pas le registre : personne ne peut tester un ton. Il tient les
quatre choses qui, elles, se vérifient.

**Il n'a qu'un domicile.** La posture vit dans `analyse.INSTRUCTION`, la base que
`parle` étend. Deux écritures d'une même règle finissent par dire deux choses, et
ce dépôt l'a payé neuf fois — dont les six refus des facultés, qui vivaient dans
trois fichiers et avaient déjà divergé.

**Il part vraiment.** Une instruction définie mais absente du bloc envoyé serait
une posture décorative. Le test lit ce que `_systeme()` construit, pas la
constante.

**Il s'arrête à la frontière du jeton.** Thomas a tranché en questionnaire : les
deux facultés qui appellent un modèle, pas la Notice. Elle est déterministe, elle
ne coûte rien, elle tourne sans clé — et ses règles sur le reproche prématuré
sont testées. Un constat chiffré sans flatterie est déjà cette posture.

**Il ne prescrit pas le corps.** La seule distinction que la posture s'autorise
est écrite dans l'instruction elle-même : un fait mesuré du corps est une donnée,
pas une excuse. Ce n'est pas une politesse, c'est la règle du dépôt sur les
chiffres faux — appeler une blessure une excuse produit une mesure fausse, et une
phrase fausse est un bug.
"""
from __future__ import annotations

import pathlib

import pytest

from singular.analyse import INSTRUCTION as BASE
from singular.parle import INSTRUCTION as CONVERSATION

RACINE = pathlib.Path(__file__).resolve().parent.parent


def _deplie(texte: str) -> str:
    """Le texte sans ses retours à la ligne : un prompt se reformule, il se replie.

    La première version de ce fichier cherchait « Tu nommes l'excuse quand tu la
    vois » et ne le trouvait pas : l'instruction coupe la ligne entre « Tu » et
    « nommes ». Un test qui tombe quand on replie un paragraphe punit la
    reformulation des messages, et ce dépôt a déjà payé ça quatre fois dans une
    seule journée.
    """
    return " ".join(texte.split())

#: Ce que la posture exige, dans les mots de l'instruction. Recopiés avec leurs
#: accents : `test_messages_recopies.py` refuse une recopie qui les perd.
EXIGENCES = (
    "Une plainte n'est pas une donnée",
    "acte mesurable et daté",
    "c'est lui qui le nomme, jamais",
    "Tu nommes l'excuse quand tu la vois",
    "un fait mesuré du corps",
    "Tu ne prescris pas ses contraintes",
)


@pytest.mark.parametrize("exigence", EXIGENCES)
def test_la_posture_vit_dans_la_base_partagee(exigence: str):
    """Donc les deux facultés la portent, sans que personne la recopie."""
    assert exigence in _deplie(BASE), f"« {exigence} » a quitté la base partagée"
    assert exigence in _deplie(CONVERSATION), "la conversation n'étend plus la base"


@pytest.mark.parametrize("exigence", EXIGENCES)
def test_la_conversation_ne_recopie_pas_la_posture(exigence: str):
    """Ce que `parle` ajoute doit être ce que seule une conversation a : les tours."""
    propre = _deplie(CONVERSATION[len(BASE):])
    assert exigence not in propre, (
        f"« {exigence} » est écrit deux fois : une fois dans la base, une fois dans "
        "l'extension de `parle`. Une règle à deux domiciles finit par dire deux choses."
    )


def test_ce_que_la_conversation_ajoute_est_le_tour_suivant():
    propre = _deplie(CONVERSATION[len(BASE):])
    assert "se réclame au tour suivant" in propre
    assert "le seul vrai échec" in propre


def test_la_posture_part_vraiment_dans_le_bloc_envoye():
    """Une instruction définie et non envoyée serait une posture décorative."""
    from singular.parle import _systeme

    envoye = _deplie("\n".join(bloc["text"] for bloc in _systeme("Notice du jour : rien.")))

    for exigence in EXIGENCES:
        assert exigence in envoye, f"« {exigence} » ne quitte pas la machine"


def test_il_peut_relire_la_posture_avant_qu_elle_parte():
    """`--blanc` affiche ce qui part. La posture en fait partie, ou elle est cachée."""
    from singular.parle import Conversation, apercu

    texte = apercu("Notice du jour : rien.", Conversation("/tmp/fil-de-test-inexistant.json"),
                   "une question")

    assert "acte mesurable et daté" in _deplie(texte)


#: Les mots par lesquels la posture se reconnaît, pour vérifier qu'ils ne
#: franchissent pas la frontière du jeton.
MOTS_DE_LA_POSTURE = ("apitoiement", "béquille", "miroir", "souveraineté", "excuse")


@pytest.mark.parametrize("mot", MOTS_DE_LA_POSTURE)
def test_le_moteur_deterministe_ne_prend_pas_cette_posture(mot: str):
    """La Notice reste un constat chiffré : c'est ce qu'il a tranché.

    Elle tourne sans clé, sans réseau et sans jeton, et ses règles sur le
    reproche prématuré existent parce qu'un reproche impossible à satisfaire lui
    a fait fermer le rapport. Le registre n'y entre pas.
    """
    notice = (RACINE / "singular" / "sage" / "notice.py").read_text(encoding="utf-8")
    assert mot not in notice.lower(), (
        f"« {mot} » est entré dans la Notice. Elle est déterministe : ce qu'elle "
        "dit doit rester un fait calculé, pas un registre."
    )
