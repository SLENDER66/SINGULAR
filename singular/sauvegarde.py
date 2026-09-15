"""Une copie du journal dont la restauration a été vérifiée avant d'être annoncée.

Le journal est le seul actif irremplaçable de ce dépôt. Le code se reprend d'un
`git clone` ; trois mois de prédictions chaînées, non. Et jusqu'ici il n'existait
aucun chemin de retour :

* `export` écrit un CSV que `import` refuse — le message de `cmd_import` le dit
  lui-même, « il est fait pour être lu, pas relu par l'outil ». Ce n'est donc pas
  une sauvegarde, c'est une lecture ;
* `import` reprend une base `.db`, mais il faut déjà en avoir une ;
* le registre de réalité nomme ce manque depuis toujours comme la seule dette du
  socle durable « qui puisse coûter des mois de journal ».

**La règle que ce module applique.** Une sauvegarde n'est réputée fiable qu'après
restauration vérifiée. Tant que la copie n'a pas été rouverte et confrontée à sa
source, elle n'est pas annoncée, et elle ne porte pas encore son nom définitif.

**Ce qui est vérifié, et ce qui ne l'est pas.** La propriété tenue ici est la
*fidélité* : la copie rend exactement ce que rend la source — mêmes décisions,
mêmes empreintes, même ordre, même verdict de chaîne. Ce n'est pas la même chose
que « le journal va bien ».

**Une chaîne rompue ne fait pas refuser la sauvegarde, et c'est délibéré.** Le
réflexe fail-closed voudrait qu'on refuse de sauvegarder un journal qui ne se
vérifie plus. Ce serait ici le pire comportement possible : le seul exemplaire
d'un journal abîmé est exactement ce qu'il faut copier avant d'y toucher, et un
garde qui supprime la copie au motif que l'original est abîmé détruit la preuve
en même temps que la donnée. Le refus est donc réservé au cas où **la copie ne
reproduit pas la source**. L'état de la chaîne est rapporté, fort et clair, mais
il ne commande pas le refus.

**Pourquoi l'API de sauvegarde de SQLite et pas une copie de fichier.** Copier
`journal.db` avec `cp` pendant qu'une écriture est en cours capture une base
déchirée, et le défaut ne se voit qu'au moment où l'on en a besoin.
`Connection.backup` prend un instantané cohérent, page par page, sous le verrou
du moteur.

**La source n'est jamais ouverte en écriture.** `lecture_seule=True` donne un
`mode=ro` que SQLite fait respecter lui-même : sauvegarder ne peut pas migrer ni
toucher l'original. C'est la leçon déjà payée par `import_from`, dont la
docstring raconte les trois `ALTER TABLE` partis sur le seul exemplaire de trois
mois de décisions.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .journal import DEFAULT_PATH, DecisionJournal
from .sqlite_support import SqliteLocation

#: À côté du journal, jamais par-dessus : `A_FAIRE.md` dit depuis longtemps que
#: le vrai risque n'est pas de perdre une histoire mais d'en écraser une.
DOSSIER_PAR_DEFAUT = Path.home() / ".singular" / "sauvegardes"

#: Les raisons de refus, et ce qu'elles veulent dire pour quelqu'un qui lit.
#:
#: Le nom porte son sujet : `REFUS` tout court est deja pris, et pas par hasard --
#: c'est la table des phrases des facultes qui appellent un modele, et
#: `tests/test_facultes_sans_fuite.py` verifie qu'aucune d'elles n'ecrit son refus
#: a la main. Deux tables du meme nom lui faisaient prendre celle-ci pour
#: celle-la, et il declarait leurs phrases jamais levees. Un nom generique dans
#: un depot qui en a deja un n'est pas un detail de style.
REFUS_DE_SAUVEGARDE = {
    "source_absente": "il n'y a pas encore de journal à sauvegarder",
    "copie_illisible": "la copie ne s'ouvre pas comme un journal : rien n'est gardé",
    "copie_infidele": "la copie ne rend pas la même chose que l'original : rien n'est gardé",
}


class SauvegardeRefusee(Exception):
    """Levée quand la copie n'a pas pu être vérifiée. Aucun fichier n'est laissé."""

    def __init__(self, raison: str, message: str) -> None:
        super().__init__(message)
        self.reason = raison


@dataclass(frozen=True)
class Sauvegarde:
    """Une sauvegarde dont la restauration a réellement été rejouée."""

    chemin: Path
    decisions: int
    empreinte: str
    chaine_intacte: bool


def _empreinte_de_tete(journal: DecisionJournal) -> str:
    """La dernière empreinte de la chaîne, ou une chaîne vide s'il n'y a rien.

    `entries()` peut trier pour l'affichage ; la tête se lit donc sur la
    dernière entrée écrite, qui est celle que `export_rows` rend en dernier.
    """
    lignes = journal.export_rows()
    return str(lignes[-1].get("fingerprint", "")) if lignes else ""


def _photographie(journal: DecisionJournal) -> tuple[list[dict], bool]:
    """Ce qu'une source et sa copie doivent rendre à l'identique."""
    return journal.export_rows(), journal.verify()


def _copier(source: Path, vers: Path) -> None:
    """L'instantané lui-même, isolé pour que son échec soit jouable.

    `sqlite3.Connection` est un type immuable : un test ne peut pas remplacer sa
    méthode `backup`. Sans cette fonction, le chemin « la copie est illisible »
    n'aurait aucun témoin -- or c'est exactement le défaut qui ne se voit que le
    jour où l'on a besoin de la sauvegarde. Une couture d'une ligne vaut mieux
    qu'un refus que personne n'a jamais vu se déclencher.

    La source est ouverte en `mode=ro` : SQLite refuse lui-même toute écriture,
    migration comprise. `Connection.backup` prend un instantané cohérent page par
    page, là où un `cp` pendant une écriture capture une base déchirée.

    Les deux côtés passent par `SqliteLocation`, comme tout ce qui ouvre une base
    ici : `tests/test_sqlite_location.py` refuse un `sqlite3.connect` direct, et
    il a raison de refuser le mien -- c'est ce point de passage unique qui
    empêche qu'un `":memory:"` se résolve en une base neuve à chaque connexion.
    """
    lecture = SqliteLocation(source, lecture_seule=True)
    ecriture = SqliteLocation(vers)
    with lecture.session() as origine, ecriture.session() as cible:
        origine.backup(cible)


def sauvegarder(chemin_journal: str | Path = DEFAULT_PATH, *,
                dossier: str | Path | None = None,
                maintenant: datetime | None = None) -> Sauvegarde:
    """Copier le journal, rouvrir la copie, la confronter, puis seulement la nommer.

    Rend la `Sauvegarde` vérifiée. Lève `SauvegardeRefusee` sans rien laisser
    derrière elle si la copie ne reproduit pas la source.
    """
    source = Path(chemin_journal)
    if not source.exists():
        raise SauvegardeRefusee("source_absente", f"aucun journal ici : {source}")

    destination = Path(dossier) if dossier is not None else DOSSIER_PAR_DEFAUT
    destination.mkdir(parents=True, exist_ok=True)

    horodatage = (maintenant or datetime.now()).strftime("%Y-%m-%d-%H%M%S")
    finale = destination / f"journal-{horodatage}.db"
    # Le nom provisoire porte l'identifiant du processus : deux sauvegardes
    # lancées dans la même seconde ne peuvent pas écrire dans le même fichier
    # temporaire, ce qui produirait deux copies mélangées et vérifiées vraies.
    partielle = destination / f".journal-{horodatage}-{os.getpid()}.partielle"

    attendu, chaine_source = _photographie(
        DecisionJournal(source, lecture_seule=True))

    try:
        _copier(source, partielle)

        try:
            copie = DecisionJournal(partielle, lecture_seule=True)
            obtenu, chaine_copie = _photographie(copie)
        except (sqlite3.DatabaseError, RuntimeError) as erreur:
            raise SauvegardeRefusee(
                "copie_illisible", f"{REFUS_DE_SAUVEGARDE['copie_illisible']} : {erreur}") from erreur

        if obtenu != attendu or chaine_copie != chaine_source:
            raise SauvegardeRefusee("copie_infidele", REFUS_DE_SAUVEGARDE["copie_infidele"])

        os.replace(partielle, finale)
    except BaseException:
        # Une copie non vérifiée ne reste pas sur le disque : elle serait prise
        # pour une sauvegarde le jour où l'on en aurait besoin.
        partielle.unlink(missing_ok=True)
        raise

    return Sauvegarde(chemin=finale, decisions=len(attendu),
                      empreinte=_empreinte_de_tete(
                          DecisionJournal(finale, lecture_seule=True)),
                      chaine_intacte=chaine_source)


__all__ = ["DOSSIER_PAR_DEFAUT", "REFUS_DE_SAUVEGARDE", "Sauvegarde", "SauvegardeRefusee", "sauvegarder"]
