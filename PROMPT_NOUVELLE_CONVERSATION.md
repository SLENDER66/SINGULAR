# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les lignes**. Ne recolle jamais `CLAUDE.md` :
il est dans le dépôt et Claude le lit tout seul.

---

Dépôt : **SLENDER66/SINGULAR** (public). Le mandat complet est dans `CLAUDE.md`
à la racine : lis-le, applique-le, ne me le fais pas répéter.

**Branche de travail : `claude/remote-control-0pu0vh`.** Elle a 9 commits
d'avance sur `claude/singular-mandate-setup-d51s9t`, qui est la branche par
défaut. Travaille sur `remote-control`. Ne merge jamais dans `main` sans mon
autorisation explicite.

## Ce que le projet est devenu — lis ça avant tout le reste

SINGULAR n'est plus seulement un audit d'architecture. C'est **une application
iPhone personnelle** qui doit m'accompagner toute ma vie, et fonctionner comme
le « Grand Sage » de *Moi quand je me réincarne en slime* : il observe, il
analyse, il conseille, **il ne décide jamais à ma place**.

Cette séparation est exactement l'invariant que le dépôt protège déjà :
penser ≠ décider ≠ autoriser ≠ exécuter. Le Sage occupe la première case.
`tests/test_sage_isolation.py` refuse tout import de la frontière d'exécution
depuis `singular/sage/` — le jour où le Sage devra vraiment agir, ce test
échouera plutôt que de laisser un serveur ou une app devenir un chemin
d'exécution.

**Ordre des facultés :** Notice (faite) → Mémoire → Analyse → Compétences.

## État vérifié au 2026-09-06 (arbre propre, tout est poussé)

- **708 tests verts**, audit de frontière propre, **CI verte jusqu'au run #1069**
  (Python 3.11 + 3.13).
- `singular/sage/` : `notice.py` (le moteur d'observation), `server.py` (app web
  installable, bibliothèque standard seule, jeton d'accès si ouverte au réseau
  local), `icon.py` (icône dessinée en Python pur).
- `ios/SingularSage/` : l'app iPhone native en SwiftUI — journal chaîné, moteur
  d'observation porté, écrans, notification locale de 8 h, tests XCTest.
  `ios/README.md` est la recette Xcode pas à pas pour un débutant.
- `tools/generate_notice_vectors.py` fige dix journaux et ce que la Notice en
  dit, **texte compris**, depuis le moteur Python. La suite Swift les rejoue et
  exige les mêmes phrases. `tests/test_notice_vectors.py` empêche ces vecteurs
  de vieillir en silence.

## Contraintes d'environnement — ne perds pas de temps à les redécouvrir

- **Aucun compilateur Swift disponible et impossible à installer** : la
  passerelle réseau refuse swift.org *et* les binaires GitHub. Le Swift du
  dépôt n'a jamais été compilé. Les vecteurs sont le filet : le premier `Cmd+U`
  sur le Mac dit si le portage est fidèle.
- **N'écris pas de Swift supplémentaire tant que je ne t'ai pas dit que le
  premier build est passé.** Empiler du code non vérifié sur du code non
  vérifié n'aide personne.
- La CI ignore `**/*.md` et `docs/**` : un commit de documentation ne déclenche
  aucun run, ce n'est pas un échec.
- `attic/` contient 22 modules et 21 tests hors périmètre. N'y travaille pas.
- `ruff check` sur tout le dépôt sort ~91 erreurs préexistantes dans de vieux
  tests. Vérifie **tes** fichiers, pas le dépôt entier, sinon tu bloques tes
  propres commits.

## Où j'en suis, moi

Je reçois un **Mac la semaine du 13 septembre 2026**. Plan arrêté :

1. Compiler l'app avec la signature **gratuite** (certificat 7 jours).
2. L'utiliser une semaine, noter ce qui me gêne et ce qui manque.
3. Prendre ensuite le compte développeur Apple à 99 €/an.

La version gratuite et la payante donnent la **même app** : seule la durée du
certificat change. La notification du matin est locale, donc elle marche sans
compte payant.

**Ce que j'attends de toi à la reprise :** rien sur l'iOS tant que je n'ai pas
dit « le build est passé ». Si je te signale un test rouge, corrige le portage.
Si je te donne des retours d'usage, traite-les. Sinon, poursuis l'audit
adversarial ci-dessous.

## Coût, pour ne pas le recalculer

Mon abonnement Claude **ne donne pas accès à l'API** — deux facturations
séparées. La faculté « Analyse » consommera ma propre clé API : ~2,5 €/mois avec
Sonnet 5 en usage modéré, ~6 €/mois avec Opus 5, ~22 €/mois en usage intense.
Plus 99 €/an chez Apple. Le moteur déterministe (Notice, journal, calibration)
fonctionne sans un seul token.

## Pistes de sécurité encore ouvertes

Fermées pendant la dernière session : l'empreinte d'artefact qui ne couvrait que
le bytecode (schéma capability v2, les lignes v1 sont révoquées) ; les attributs
de classe sans `__code__` ; `attach()` et `revoke()` qui échouaient en
fail-open ; le scan d'intégrité global qui pouvait fermer la frontière pour
toujours (désormais borné à la mission, avec index) ; l'empreinte d'artefact du
registre d'amélioration qui valait une adresse mémoire (schéma v3) ; la chaîne
du journal cassée par un coût en entier.

Restent ouvertes :

1. Ce à quoi **un nom global se résout** n'est pas couvert par l'empreinte de
   capability. Limite assumée et testée : qui peut réécrire les globals d'un
   module change le comportement sans changer l'empreinte.
2. Un objet qui ne déclare pas `artifact_identity()` reste identifié par sa
   seule classe : son état d'instance n'est pas couvert (opt-in assumé, testé).
3. L'auditeur de frontière ne voit pas un module à qui l'on **passe** un objet
   frontière déjà construit. Vérifié : ça ne permet pas de forger une autorité.
   C'est de l'hygiène, pas une escalade.
4. `reconcile_effect_validated` n'appelle pas `_assert_policy_unchanged`, à la
   différence de `execute_validated` et `execute_effect_validated`. C'est
   probablement voulu — réconcilier établit ce qui s'est déjà passé plutôt que
   d'agir à nouveau, et `_authorize_reconciliation` est délibérément plus
   souple — mais **aucun test ne fixe ce raisonnement**. À trancher : le pinner
   ou le corriger.
5. `DurableIntegrityChecker.check()` sans argument (la vue base entière) n'a
   plus aucun appelant en production depuis que la frontière est bornée à la
   mission. C'est l'outil de l'opérateur ; rien ne le lance automatiquement au
   démarrage.

## Décision que je n'ai pas tranchée

`ActionRequest.capability` — la capacité de gouvernance **nommée**, pas le
jeton `cap_` — vaut `None` par défaut. Une action sans capacité n'est jugée que
par les règles génériques de risque et de sensibilité ; une action qui en
déclare une reçoit en plus les plafonds de cette capacité. Le pipeline validé
n'en exige pas. **Faut-il la rendre obligatoire pour toute action exécutable ?**
Plus fail-closed, mais ça refuserait des actions qui passent aujourd'hui.

## Contexte personnel (ne me le redemande pas)

- Débutant. PC Windows aujourd'hui, **Mac à partir de la semaine du 13/09**,
  iPhone. Explique les commandes pas à pas, ne suppose ni Git configuré ni
  Python installé.
- ~30 h/semaine. Objectif : SINGULAR utile puis rentable en 1–2 ans.
- Parle-moi **en français**.
- Économise mes tokens : droit au but, pas de récapitulatif long, pas de
  re-vérification de ce qui est écrit ci-dessus.

## Méthode

Inspecte → corrige → teste → commits atomiques → pousse → enchaîne. Décide
seul de ce qui est déterminé. Ne m'interromps que pour une décision humaine,
métier ou personnelle, sous forme de questionnaire.

---

## Ce que je dois faire moi-même

Rien sur GitHub. Sur le Mac, quand il arrive : suivre `ios/README.md`.
