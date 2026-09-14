"""L'expérience Genesis, en entier, sur les fichiers réels de ce dépôt.

    python3 tools/genesis_experiment.py

Elle ne coûte rien : pas de modèle, pas de clé, pas de réseau. C'est la
condition pour qu'elle tourne dans le CI, donc pour qu'elle tourne du tout --
le mandat garde le souvenir d'une application finie et jamais lancée, et une
expérience qui demanderait cinq dollars de crédit finirait pareil.

Elle peut rendre un verdict négatif. C'est même le seul intérêt d'avoir un banc.
"""
from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from singular.genesis import Registre, Trajectoire, executer  # noqa: E402
from singular.genesis.bench import banc, constater_naissance  # noqa: E402
from singular.genesis.missions import (GAMMA_ABIMEE, GAMMA_APPRENTISSAGE,  # noqa: E402
                                       GAMMA_CONTROLE, LECTEUR_APPRIS, alpha,
                                       apprendre_de_gamma, apprendre_le_egal, beta, delta,
                                       epsilon, gamma, prouver_emploi, resoudre,
                                       sources_du_depot, zeta)


def _solveur(mission, trajectoire, registre):
    return resoudre(mission, trajectoire, registre)


def _ligne(resultat) -> str:
    verdict = "vérifiée" if resultat.verifie else "RATÉE"
    return (f"  {resultat.mission:<16} {verdict:<9} coût {resultat.cout:>5}  "
            f"erreurs {resultat.erreurs:<3} récupérations {resultat.recuperations:<3} "
            f"humain {resultat.interventions_humaines}")


def experience(racine: Path) -> dict:
    """Déroule ALPHA, BETA, GAMMA, puis mesure ce que GAMMA a laissé."""
    sources = sources_du_depot(racine)
    registre = Registre()
    resultats = []

    for mission in (alpha(sources), beta(sources)):
        resultats.append(executer(mission, lambda m, t: resoudre(m, t, registre)))

    avant = executer(gamma(GAMMA_APPRENTISSAGE, nom="GAMMA (sans)"),
                     lambda m, t: resoudre(m, t, registre))
    resultats.append(avant)

    acquisition = Trajectoire("GAMMA-acquisition")
    acquise = apprendre_de_gamma(registre, acquisition)

    apres = executer(gamma(GAMMA_APPRENTISSAGE, nom="GAMMA (avec)"),
                     lambda m, t: resoudre(m, t, registre))
    resultats.append(apres)
    if acquise:
        prouver_emploi(registre, instance="matin", domaine="releve",
                       abimee=False, reussi=apres.verifie)

    naissance = constater_naissance(
        gamma(GAMMA_CONTROLE, nom="CONTROLE", attendu="téléphone"),
        _solveur, registre, instance="soir", apprises_sur={"matin"})
    prouver_emploi(registre, instance="soir", domaine="releve", abimee=False,
                   reussi=naissance.comparaison.experimente.verifie)

    echelle = _gravir(registre, sources)
    composition = _composer(registre, sources)
    return {"resultats": resultats, "acquisition": acquisition, "acquise": acquise,
            "naissance": naissance, "registre": registre, "echelle": echelle,
            "composition": composition}


def _composer(registre: Registre, sources: dict) -> dict:
    """Deux capacités se composent-elles ? Mesuré, jamais supposé.

    ZETA demande une valeur à `.github/workflows/ci.yml` et une autre à
    `pytest.ini`. Le premier n'est lisible que par le lecteur `': '` ; le second
    par **rien** de ce que le dépôt savait faire, ni par ce premier lecteur. Une
    capacité seule ne suffit donc pas, et la ligne de base du banc est ici un
    registre à une capacité, pas un registre vide.
    """
    une = Registre()
    apprendre_de_gamma(une, Trajectoire("rappel"))
    apprendre_le_egal(sources, registre, Trajectoire("GAMMA-bis"))
    comparaison = banc(zeta(sources), _solveur, registre, base_registre=une)
    return {"comparaison": comparaison, "registre": registre}


def _gravir(registre: Registre, sources: dict) -> list[tuple[str, str, bool, str]]:
    """Les barreaux, puis la chute -- et c'est la chute qui apprend quelque chose.

    Monter jusqu'à E5 dans un script ne prouve rien : quand on a les instances
    sous la main, une échelle se gravit. Ce qu'elle vaut se lit à ce qu'elle
    refuse. Le dernier emploi est donc un échec réel, sur un vrai fichier que ce
    lecteur ne sait pas lire, et il faut voir le niveau retomber.
    """
    barreaux: list[tuple[str, str, bool, str]] = []
    emplois = (
        ("ci", "config", False, delta(sources), "le workflow réel du dépôt"),
        ("abimee", "releve", True, gamma(GAMMA_ABIMEE), "un relevé arraché"),
        ("pyproject", "config", False, epsilon(sources), "un format qu'il ne tient pas"),
    )
    for instance, domaine, abimee, mission, quoi in emplois:
        resultat = executer(mission, lambda m, t: resoudre(m, t, registre))
        # Ce qu'on enregistre est ce que **la capacité** a fait, pas ce que la
        # mission a obtenu. Le solveur sait se rabattre : EPSILON réussit par le
        # tâtonnement alors que le lecteur appris n'a rien su en tirer, et
        # créditer la capacité de ce succès-là ferait monter un niveau de preuve
        # sur le travail d'un autre.
        repondu = LECTEUR_APPRIS in resultat.capacites_reutilisees
        prouver_emploi(registre, instance=instance, domaine=domaine, abimee=abimee,
                       reussi=repondu)
        barreaux.append((instance, registre.chercher(LECTEUR_APPRIS).niveau,
                         repondu, quoi))
    return barreaux


def afficher(rapport: dict) -> None:
    print("\n=== AZAZEL GENESIS — les trois missions ===\n")
    for resultat in rapport["resultats"]:
        print(_ligne(resultat))

    print("\n=== GAMMA — comment la capacité a été acquise ===\n")
    for pas in rapport["acquisition"].pas:
        detail = f"  ({pas.detail})" if pas.detail else ""
        print(f"  {pas.genre.value:<14} {pas.quoi}{detail}")

    print("\n=== l'échelle de preuve, et sa chute ===\n")
    for instance, niveau, reussi, quoi in rapport["echelle"]:
        verdict = "tenu " if reussi else "RATÉ "
        print(f"  {instance:<12} {verdict} {quoi:<34} → {niveau}")
    print("  Un seul échec ramène à E2 : « vérifiée » et « robuste » sont des"
          "\n  affirmations de fiabilité, pas des compteurs de succès.")

    print("\n=== le registre ===\n")
    for ligne in rapport["registre"].rapport():
        print(f"  {ligne['nom']}  {ligne['niveau']} — {ligne['sens']}")
        print(f"    artefact {ligne['empreinte'][:16]}…  version {ligne['version']}  "
              f"issue de {ligne['provenance']}  employée {ligne['reutilisations']}×  "
              f"échecs {ligne['echecs']}")

    composition = rapport["composition"]["comparaison"]
    print("\n=== la composition — ZETA, qu'aucune capacité ne règle seule ===\n")
    print("  ci.yml n'est lisible que par le lecteur ': ' ; pytest.ini par aucun")
    print("  lecteur du dépôt, ni par celui-là. Ligne de base : une capacité.\n")
    for ecart in composition.ecarts:
        print(f"  {ecart.axe:<24} {ecart.avant:>6} → {ecart.apres:<6} ({ecart.delta:+})")
    print(f"\n  verdict : {composition.verdict} — {composition.pourquoi}")
    print(f"  capacités employées : {', '.join(composition.capacites_reutilisees) or 'aucune'}")

    naissance = rapport["naissance"]
    print("\n=== le test de naissance — mission de contrôle, instance jamais vue ===\n")
    for ecart in naissance.comparaison.ecarts:
        print(f"  {ecart.axe:<24} {ecart.avant:>6} → {ecart.apres:<6} ({ecart.delta:+})")
    print(f"\n  verdict du banc : {naissance.comparaison.verdict} — "
          f"{naissance.comparaison.pourquoi}")
    print(f"  capacités employées : {', '.join(naissance.capacites) or 'aucune'}")
    print(f"\n  NAISSANCE CONSTATÉE : {'oui' if naissance.ne else 'non'} — {naissance.pourquoi}")
    print("\n  Ce que ça ne dit pas : une capacité, deux domaines, cinq instances."
          "\n  L'hypothèse tient sur ce cas ; elle n'est pas démontrée en général.\n")


def main() -> int:
    rapport = experience(RACINE)
    afficher(rapport)
    naissance = rapport["naissance"]
    if not naissance.ne:
        print("  L'expérience n'a pas constaté de naissance. C'est une donnée, pas un bug.")
        return 1
    if rapport["registre"].chercher(LECTEUR_APPRIS) is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
