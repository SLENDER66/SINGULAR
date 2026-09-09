"""Ce qu'il tape, verifie dans sa langue, avant que le journal refuse en anglais.

Les regles sont celles de `DecisionJournal.add` : une probabilite strictement
entre 0 et 1, des heures positives, un horizon d'au moins un jour, un gain qui
n'est pas un cout. Le journal les fait respecter et leve en anglais -- c'est
son contrat de bibliotheque, teste comme tel.

Mais ce message-la remonte jusqu'a lui. Au clavier il lisait
`probability must be strictly between 0 and 1` ; sur son telephone,
`expected_gain_eur cannot be negative: a cost is not a gain`. Il debute en
code, il est francais, et ces phrases ne disent pas quoi faire.

Chaque surface s'etait donc mise a valider de son cote : le clavier en
francais, le formulaire par des attributs HTML, le serveur pas du tout. Trois
ecritures de la meme regle, dont une qui laissait passer le gain negatif.

Ce module est le seul endroit ou la regle est dite en francais.
`tests/test_saisie_au_clavier.py` verifie que ce qui est accepte ici est
exactement ce que le journal accepte : deux ecritures d'une meme regle
finissent par diverger, et celle qui se tromperait lui ferait perdre sa
saisie.

Les messages passent par la console de Windows : `test_windows_console.py`
scanne ce fichier, et refuse un caractere qu'elle ne sait pas afficher.
"""
from __future__ import annotations

from math import isfinite


def nombre(brut: object) -> float:
    """Un nombre tel qu'il le tape : « 0,75 » et « 1 500 » comptent.

    Il est en France, sur un clavier francais : la virgule decimale est ce qui
    vient naturellement, et le clavier iOS insere une espace fine insecable
    comme separateur de milliers -- invisible a l'oeil, fatale a `float()`.
    Toutes les espaces sont retirees par ce qu'elles sont, sans en nommer
    aucune : la console de Windows ne sait pas ecrire la fine insecable.
    """
    texte = "".join(c for c in str(brut) if not c.isspace()).replace(",", ".")
    try:
        return float(texte)
    except ValueError:
        raise ValueError(f"« {brut} » n'est pas un nombre") from None


def entier(brut: object) -> int:
    return int(nombre(brut))


def verifie_probabilite(valeur: float) -> None:
    """Entre 0.05 et 0.95, et pas en pourcents.

    Taper « 75 » en pensant pourcents passait les six questions suivantes du
    clavier, puis echouait a l'ecriture -- en anglais, et apres coup : tout ce
    qu'il venait de saisir etait perdu.
    """
    if not isfinite(valeur):
        raise ValueError("une probabilite, pas l'infini")
    # Strictement entre 1 et 100 : « 1 » veut dire la certitude, pas 1 %, et
    # « 100 » aussi. Les lire comme des pourcents faisait conseiller « pour
    # 100 %, ecris 1 » -- un conseil que la ligne suivante refuse.
    if 1 < valeur < 100:
        raise ValueError(
            f"entre 0.05 et 0.95, pas en pourcents - pour {valeur:g} %, ecris "
            f"{valeur / 100:g}")
    if not 0 < valeur < 1:
        raise ValueError("entre 0.05 et 0.95 : une certitude ne peut pas avoir tort, "
                         "une impossibilite non plus")


def verifie_heures(valeur: float) -> None:
    if not isfinite(valeur):
        raise ValueError("un nombre d'heures, pas l'infini")
    if valeur < 0:
        raise ValueError("des heures ne se comptent pas en negatif")


def verifie_jours(valeur: int) -> None:
    if valeur < 1:
        raise ValueError("au moins un jour, sinon rien ne peut etre verifie")


def verifie_gain(valeur: float | None) -> None:
    """Vide veut dire « non chiffre », jamais « zero ». Negatif ne veut rien dire.

    Le formulaire du telephone n'avait aucune borne sur ce champ -- il est en
    texte libre, exprès, pour que « vide » reste possible. Taper « -100 » en
    pensant a un cout renvoyait donc
    `expected_gain_eur cannot be negative: a cost is not a gain`, sur son
    telephone, en anglais. Le clavier, lui, repondait deja en francais.
    """
    if valeur is None:
        return
    if not isfinite(valeur):
        raise ValueError("un montant, pas l'infini")
    if valeur < 0:
        raise ValueError("un cout n'est pas un gain : laisse vide si tu ne sais pas")


#: Ce que voit quelqu'un qui tranche deux fois la meme decision.
#:
#: Le cas est banal : deux onglets ouverts, un double appui sur un telephone,
#: ou la ligne de commande apres l'app. Le journal refuse -- c'est sa promesse
#: centrale, l'histoire ne se reecrit pas -- et il refusait en anglais :
#: `DEC-24bfbaeb was already resolved as HAPPENED; history is not editable`.
#: L'app avait sa traduction, ecrite chez elle ; le clavier et le serveur
#: n'avaient rien. La phrase vit ici, les trois la lisent, et
#: `tests/test_saisie_au_clavier.py` verifie que la copie JavaScript -- la
#: seule qui ne peut pas importer ce fichier -- dit encore la meme chose.
CONFLIT = ("Cette décision a déjà été tranchée. Ferme et rouvre pour voir le "
           "verdict enregistré.")


def introuvable(entry_id: str) -> str:
    """Un identifiant qui n'est dans aucune ligne du journal.

    La ligne de commande affichait `'DEC-inconnu'`, guillemets compris : le
    `repr` d'une cle absente, qui n'explique rien a quelqu'un qui vient de
    taper de travers.
    """
    return f"{entry_id} n'est dans aucune ligne de ce journal (python -m singular list)."


__all__ = ["CONFLIT", "entier", "introuvable", "nombre", "verifie_gain", "verifie_heures",
           "verifie_jours", "verifie_probabilite"]
