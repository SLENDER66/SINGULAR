"""Ecrire un fichier d'etat sans pouvoir le perdre en tombant.

Trois fichiers portent quelque chose qu'il ne peut pas reconstituer : son fil
de conversation, sa cle d'acces, et -- dans le prototype de suivi -- ses
candidatures. Les trois etaient ecrits par un `write_text`, qui tronque le
fichier puis ecrit dedans. Entre les deux, il n'y a rien.

Une interruption a cet instant -- Ctrl+C, un portable qu'on referme, une
coupure -- laisse un JSON a moitie ecrit. Reproduit sur le suivi de
candidatures : l'outil refuse alors de demarrer et renvoie une erreur de
parseur JSON a quelqu'un qui debute en code. Son historique n'est pas perdu au
sens strict, il est juste illisible, ce qui revient au meme.

`Quota` faisait deja l'ecriture en deux temps, pour cette raison exacte. C'est
la troisieme fois que le meme oubli se paie, donc il n'y a plus qu'un endroit
qui sait ecrire, et `test_ecriture_atomique.py` refuse qu'un fichier d'etat
soit ecrit autrement.

Bibliotheque standard seule : ce module est importe par le coeur du Sage, que
`test_sage_independence.py` doit pouvoir lancer sur une machine debranchee.
"""
from __future__ import annotations

import os
from pathlib import Path


def ecrire_atomique(chemin: Path, texte: str, *, permissions: int | None = None) -> None:
    """Ecrit tout, ou rien. Le fichier n'existe jamais a moitie.

    On ecrit a cote, on ferme, puis on remplace : `os.replace` est atomique sur
    Windows comme sur Unix, donc une interruption laisse soit l'ancien fichier
    intact, soit le nouveau complet, jamais un melange des deux.

    Le fichier provisoire porte le numero du processus. Il portait un nom fixe
    dans `Quota`, et deux ecrivains simultanes s'en disputaient un seul : le
    second retrouvait le fichier deja deplace et levait `FileNotFoundError`.
    Mesure sur huit processus : neuf plantages sur quarante ecritures.

    `permissions` pose les droits **avant** d'ecrire, pas apres. La cle d'acces
    etait ecrite en clair puis resserree a 0600 : entre les deux, le secret
    etait lisible par tout le monde. La fenetre est courte et elle existe.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_name(f"{chemin.name}.{os.getpid()}.tmp")
    if permissions is None:
        descripteur = os.open(provisoire, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    else:
        descripteur = os.open(provisoire, os.O_CREAT | os.O_EXCL | os.O_WRONLY, permissions)
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(texte)
    except BaseException:
        # Y compris KeyboardInterrupt : c'est precisement l'interruption dont
        # ce module protege, et laisser trainer le provisoire ferait echouer
        # l'ecriture suivante sur `O_EXCL`.
        provisoire.unlink(missing_ok=True)
        raise
    os.replace(provisoire, chemin)


__all__ = ["ecrire_atomique"]
