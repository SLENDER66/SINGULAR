# Prompt de reprise — à copier/coller dans une nouvelle conversation

> Colle **uniquement le bloc ci-dessous**. Il suffit : ne recolle jamais le mandat
> CLAUDE.md, il est déjà dans le dépôt et Claude le lit tout seul.

---

Dépôt : SLENDER66/SINGULAR (public). Branche de travail et branche par défaut :
`claude/singular-mandate-setup-d51s9t`. Le mandat complet est dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter.

État vérifié au 2026-09-05 (commit 3aa6ea1, poussé, arbre propre) :
- 572 tests passent, audit de frontière propre, CI verte (run #1036, Python 3.11 + 3.13).
- La frontière d'exécution est fail-closed : ValidatedTrajectoryDecision → attestation
  durable → capability (fingerprint d'artefact) → lease → effet externe → outcome ledger.
- 22 modules et 21 fichiers de test hors périmètre sont parqués dans `attic/`.
- `A_FAIRE.md` liste les 3 actions que moi seul peux faire sur GitHub.

Contexte personnel (ne me le redemande pas) :
- Je suis débutant. J'ai un **PC sous Windows** et un téléphone. Je peux donc exécuter
  des commandes, mais explique-les-moi pas à pas (PowerShell, chemins Windows) : ne
  suppose ni Linux, ni Git déjà configuré, ni Python déjà installé.
- ~30 h/semaine disponibles. Objectif : que SINGULAR devienne utile puis rentable en 1–2 ans.
- Ne merge jamais dans `main` sans mon autorisation explicite.
- Fais attention à ma limite d'utilisation : va droit au but, pas de récapitulatif long,
  pas de re-vérification de ce qui est déjà établi ci-dessus.

Travaille en autonomie. Ordre de priorité si tu dois choisir :
1. LICENSE manquante (le README y fait référence, le dépôt est public).
2. Nettoyage des 46 branches distantes : elles ne pointent que sur **8 commits distincts**
   et `feat/human-trajectory-engine` a un **historique séparé** de la branche de travail.
   Ne supprime donc pas tout : garde une branche par tip distinct, supprime les doublons.
3. Points ouverts dans le code : l'approbation humaine n'est pas un canal d'autorisation
   (`_validate_approval_binding` inatteignable depuis un chemin validé) ;
   `ImprovementCandidate.safety_critical` est un drapeau auto-déclaré ; `route()` n'écrit
   aucun événement d'audit sur son chemin normal.

Méthode : inspecte → corrige → teste → commits atomiques → pousse → enchaîne.
Pose-moi les questions sous forme de questionnaire, seulement si une décision humaine est
réellement nécessaire.

---

## Pourquoi ce prompt consomme peu

- Il ne recopie pas le mandat (≈900 lignes) : il pointe vers `CLAUDE.md`.
- Il donne l'état déjà vérifié, donc Claude ne refait pas l'inspection complète.
- Il fixe le contexte personnel une fois pour toutes (Windows, débutant, limites).
- Il donne un ordre de priorité, donc pas d'aller-retour pour décider quoi faire.
