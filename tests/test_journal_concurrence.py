"""Trancher une décision deux fois doit être impossible, pas seulement rare.

« A journal you can edit afterwards teaches you nothing » — c'est la phrase
d'ouverture de `journal.py`, et elle ne tenait qu'en l'absence de concurrence.

`resolve()` lisait le statut, refusait si la décision n'était plus ouverte,
puis écrivait. Trois gestes, aucun verrou : deux processus lisaient tous deux
OPEN, passaient tous deux le refus, et écrivaient tous deux. Mesuré avant
correction — quatre processus, deux verdicts contradictoires acceptés, et
celui qui perdait la course s'entendait répondre que son verdict était
enregistré alors que le journal disait l'inverse.

Le scénario n'est pas exotique : le Sage sert un bouton « trancher » sur le
téléphone, et la ligne de commande fait la même chose depuis une autre
fenêtre. Un double appui suffit.

Ces tests passent par de vrais processus. Des fils d'exécution partageraient
le verrou du même interpréteur et prouveraient beaucoup moins.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time

import pytest

from singular.journal import DecisionJournal, Status, Tier

#: Assez pour que les processus soient tous en attente quand le top part.
DELAI_DEMARRAGE = 0.4


def _course(tmp_path, appel: str, nombre: int = 6) -> list[str]:
    """Lance `nombre` processus qui exécutent `appel` exactement en même temps.

    Sans barrière ils démarrent en file indienne et ne se croisent jamais : un
    test de concurrence qui ne peut pas échouer donne une confiance gratuite,
    et celui de la migration est d'abord passé dans cet état-là.
    """
    chemin = tmp_path / "j.db"
    journal = DecisionJournal(chemin)
    entree = journal.add(
        title="Postuler", action="Envoyer le CV", predicted="Un entretien",
        probability=0.6, tier=Tier.REVENUS, cost_hours=2, horizon_days=1,
    )
    depart = tmp_path / "top"

    bloc = textwrap.dedent(f'''
        import os, time
        while not os.path.exists(r"{depart}"):
            time.sleep(0.001)
        from singular.journal import DecisionJournal
        journal = DecisionJournal(r"{chemin}")
        try:
            resultat = {appel}
            print("ACCEPTE", resultat.status.value)
        except PermissionError:
            print("REFUSE")
    ''').replace("ENTREE", entree.entry_id)

    processus = [
        subprocess.Popen([sys.executable, "-c", bloc], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
        for _ in range(nombre)
    ]
    time.sleep(DELAI_DEMARRAGE)
    depart.write_text("go", encoding="utf-8")
    sorties = [p.communicate()[0].strip() for p in processus]
    return sorties


def _acceptes(sorties: list[str]) -> list[str]:
    return [s.splitlines()[-1] for s in sorties if "ACCEPTE" in s]


def test_une_decision_ne_peut_etre_tranchee_qu_une_fois(tmp_path) -> None:
    sorties = _course(
        tmp_path,
        'journal.resolve("ENTREE", happened=True, lesson="verdict")',
    )
    acceptes = _acceptes(sorties)

    assert len(acceptes) == 1, (
        f"{len(acceptes)} verdicts acceptes sur la meme decision :\n"
        + "\n".join(s[-200:] for s in sorties)
    )


def test_ce_qu_on_repond_au_gagnant_est_ce_que_le_journal_garde(tmp_path) -> None:
    """Le pire cas mesuré : « enregistré » répondu, l'inverse écrit."""
    sorties = _course(
        tmp_path,
        'journal.resolve("ENTREE", happened=({i} % 2 == 0), lesson="verdict")'.replace(
            "{i}", "os.getpid()"),
    )
    acceptes = _acceptes(sorties)
    assert len(acceptes) == 1

    annonce = acceptes[0].split()[1]
    stocke = DecisionJournal(tmp_path / "j.db").entries()[0].status.value
    assert annonce == stocke, f"annonce {annonce}, stocke {stocke}"


def test_abandonner_deux_fois_est_refuse_aussi(tmp_path) -> None:
    """`abandon()` portait exactement la même course, et le même refus muet."""
    sorties = _course(tmp_path, 'journal.abandon("ENTREE", reason="je laisse tomber")')

    assert len(_acceptes(sorties)) == 1


def test_trancher_et_abandonner_en_meme_temps_n_en_laisse_passer_qu_un(tmp_path) -> None:
    """Les deux chemins ecrivent le meme champ : le verrou doit etre le meme."""
    sorties = _course(
        tmp_path,
        'journal.abandon("ENTREE", reason="stop") if os.getpid() % 2'
        ' else journal.resolve("ENTREE", happened=True, lesson="verdict")',
    )

    assert len(_acceptes(sorties)) == 1


@pytest.mark.parametrize("statut", [Status.HAPPENED, Status.ABANDONED])
def test_le_refus_reste_lisible_sans_concurrence(tmp_path, statut: Status) -> None:
    """La correction ne doit pas remplacer le message clair par un message de course."""
    journal = DecisionJournal(tmp_path / "j.db")
    entree = journal.add(title="X", action="Y", predicted="Z", probability=0.6,
                         tier=Tier.REVENUS, cost_hours=1, horizon_days=1)
    if statut is Status.HAPPENED:
        journal.resolve(entree.entry_id, happened=True)
    else:
        journal.abandon(entree.entry_id, reason="stop")

    with pytest.raises(PermissionError, match="already resolved"):
        journal.resolve(entree.entry_id, happened=False)
